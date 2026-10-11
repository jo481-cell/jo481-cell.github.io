import { randomBytes, createHash, createHmac, timingSafeEqual } from 'node:crypto';
import sharp from 'sharp';
import type { VercelRequest, VercelResponse } from '@vercel/node';

const origin = () => process.env.PUBLIC_SITE_ORIGIN || 'https://hyruleatlas.com';
const languages = ['en','fr','es','ja','zh'];
const categories = ['announcements','help','theories','general'];
const publicKey = () => process.env.SUPABASE_PUBLISHABLE_KEY || process.env.SUPABASE_ANON_KEY || '';
const secretKey = () => process.env.SUPABASE_SECRET_KEY || process.env.SUPABASE_SERVICE_ROLE_KEY || '';
const databaseReady = () => Boolean(process.env.SUPABASE_URL && publicKey() && secretKey());
const modernKey = (key:string) => key.startsWith('sb_publishable_') || key.startsWith('sb_secret_');
function supabaseHeaders(admin:boolean,token?:string):Record<string,string>{
 const key=admin?secretKey():publicKey();
 const bearer=token && token!==key?token:(modernKey(key)?'':key);
 return {apikey:key,'User-Agent':'hyrule-atlas-community/1.0',...(bearer?{Authorization:`Bearer ${bearer}`}:{})};
}
const mailReady = () => Boolean(process.env.RESEND_API_KEY && process.env.EMAIL_FROM);
const botProtectionReady = () => Boolean(process.env.TURNSTILE_SITE_KEY && process.env.TURNSTILE_SECRET_KEY);
const hash = (v:string) => createHash('sha256').update(v).digest('hex');
const uuid = (v:unknown) => typeof v === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v);
class Failure extends Error { constructor(public status:number, message:string){super(message)} }
function text(v:unknown, min:number, max:number){if(typeof v!=='string'||v.trim().length<min||v.trim().length>max)throw new Failure(400,'Please check the required fields.');return v.trim()}
function email(v:unknown){const s=text(v,5,254).toLowerCase();if(!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s))throw new Failure(400,'Please enter a valid email address.');return s}
function password(v:unknown){if(typeof v!=='string'||v.length<12||v.length>128)throw new Failure(400,'Please check the required fields.');return v}
function locale(v:unknown){return languages.includes(String(v))?String(v):'en'}
function consent(v:unknown){return v===true||v==='true'}
function safeUrl(v:unknown){if(!v)return '';const s=text(v,0,500);try{const u=new URL(s);if(u.protocol!=='https:')throw 0;return u.href}catch{throw new Failure(400,'Portfolio links must use HTTPS.')}}
function cleanBody(v:unknown){const s=text(v,10,10000);if((s.match(/https?:\/\//g)||[]).length>3)throw new Failure(400,'Please use at most three links per post.');return s}
function escape(v:string){return v.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]!))}
function unsubscribeToken(id:string){if((process.env.NEWSLETTER_TOKEN_SECRET||'').length<32)throw new Failure(503,'Newsletter sending is not configured.');return createHmac('sha256',process.env.NEWSLETTER_TOKEN_SECRET!).update(`unsubscribe:${id}`).digest('hex')}
const emailCopy:Record<string,{account:string,continue:string,subscribe:string,confirm:string,subject:string,intro:string,ignore:string,unsubscribe:string,cancelled:string}>={
 en:{account:'Continue to your Hyrule Atlas account.',continue:'Continue',subscribe:'Receive the weekly Hyrule Atlas newsletter?',confirm:'Confirm my subscription',subject:'Confirm your Hyrule Atlas newsletter',intro:'Confirm your subscription to our weekly Zelda letter.',ignore:'If you did not request this, ignore this message. The link expires in 48 hours.',unsubscribe:'Unsubscribe',cancelled:'Your newsletter subscription has been cancelled.'},
 fr:{account:'Continuer vers votre compte Hyrule Atlas.',continue:'Continuer',subscribe:'Recevoir la lettre hebdomadaire Hyrule Atlas ?',confirm:'Confirmer mon abonnement',subject:'Confirmez votre abonnement à Hyrule Atlas',intro:'Confirmez votre abonnement à notre lettre hebdomadaire Zelda.',ignore:'Si vous n’avez pas fait cette demande, ignorez ce message. Le lien expire dans 48 heures.',unsubscribe:'Se désabonner',cancelled:'Votre abonnement à la lettre a été annulé.'},
 es:{account:'Continúa a tu cuenta de Hyrule Atlas.',continue:'Continuar',subscribe:'¿Recibir la carta semanal de Hyrule Atlas?',confirm:'Confirmar mi suscripción',subject:'Confirma tu suscripción a Hyrule Atlas',intro:'Confirma tu suscripción a nuestra carta semanal de Zelda.',ignore:'Si no solicitaste esto, ignora este mensaje. El enlace caduca en 48 horas.',unsubscribe:'Cancelar suscripción',cancelled:'Tu suscripción ha sido cancelada.'},
 ja:{account:'Hyrule Atlas のアカウントに進みます。',continue:'続ける',subscribe:'Hyrule Atlas の週刊ニュースレターを受け取りますか？',confirm:'購読を確認する',subject:'Hyrule Atlas の購読を確認してください',intro:'ゼルダの週刊ニュースレターの購読を確認してください。',ignore:'心当たりがない場合は、このメールを無視してください。リンクは48時間で失効します。',unsubscribe:'購読を解除',cancelled:'ニュースレターの購読を解除しました。'},
 zh:{account:'继续前往你的 Hyrule Atlas 账户。',continue:'继续',subscribe:'接收 Hyrule Atlas 每周通讯？',confirm:'确认订阅',subject:'请确认订阅 Hyrule Atlas 通讯',intro:'请确认订阅我们的塞尔达每周通讯。',ignore:'如果你没有提出此请求，请忽略此邮件。链接将在48小时后失效。',unsubscribe:'取消订阅',cancelled:'你的通讯订阅已取消。'}
};
const localizedPath=(language:string,path:string)=>`${origin()}${language==='en'?'':`/${language}`}${path}`;
function confirmationPage(res:VercelResponse, action:string, title:string, label:string,language='en'){res.setHeader('Content-Type','text/html; charset=utf-8');return res.send(`<html lang="${language==='zh'?'zh-Hans':language}"><meta name="viewport" content="width=device-width"><title>Hyrule Atlas · Confirmation</title><body style="font-family:Georgia,serif;max-width:600px;margin:10vh auto;padding:24px;color:#16352e"><h1>Hyrule Atlas</h1><p>${escape(title)}</p><form method="post" action="${escape(action)}"><button style="font:inherit;padding:12px 24px">${escape(label)}</button></form></body></html>`)}
export function newsletterHtml(body:string,sources:any[],language='fr'){
 const inline=(value:string)=>escape(value).replace(/\[([^\]\n]+)\]\((https:\/\/[^\s)]+)\)/g,(_all,label,url)=>`<a href="${url}" style="color:#17634e">${label}</a>`).replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>');
 const blocks=body.split(/\n\s*\n/).map(block=>{if(/^#{1,3} /.test(block))return `<h2 style="font-size:23px;line-height:1.3">${inline(block.replace(/^#{1,3} /,''))}</h2>`;if(block.split('\n').every(line=>/^[-*] /.test(line)))return `<ul>${block.split('\n').map(line=>`<li>${inline(line.slice(2))}</li>`).join('')}</ul>`;return `<p>${inline(block).replace(/\n/g,'<br>')}</p>`});
 const sourceTitle:Record<string,string>={fr:'Sources vérifiées',en:'Verified sources',es:'Fuentes verificadas',ja:'確認済みの出典',zh:'已核实来源'};
 return blocks.join('')+`<h2 style="font-size:20px">${sourceTitle[language]||sourceTitle.en}</h2><ul>${sources.map(source=>`<li><a href="${escape(safeUrl(source.url))}" style="color:#17634e">${escape(source.title)}</a></li>`).join('')}</ul>`;
}
async function removeArtImages(keys:string[]){
 if(!keys.length)return;
 const failure=()=>new Failure(503,'Your images could not be removed yet. Please contact the team.');
 const removal=await fetch(`${process.env.SUPABASE_URL}/storage/v1/object/fanart-private`,{method:'DELETE',headers:{...supabaseHeaders(true),'Content-Type':'application/json'},body:JSON.stringify({prefixes:keys}),signal:AbortSignal.timeout(12000)}).catch(()=>{throw failure()});
 if(!removal.ok)throw failure();
 // Storage can return 200 with [] when a file was already absent. The GET is the
 // actual privacy check, including after an apparently successful DELETE.
 for(const key of keys){
  const probe=await fetch(`${process.env.SUPABASE_URL}/storage/v1/object/fanart-private/${key}`,{headers:supabaseHeaders(true),signal:AbortSignal.timeout(12000)}).catch(()=>{throw failure()});
  await probe.body?.cancel().catch(()=>null);
  if(probe.status!==404)throw failure();
 }
}

async function upstream(path:string, token:string, method='GET', body?:unknown, admin=false){
 const response=await fetch(`${process.env.SUPABASE_URL}${path}`,{method,headers:{...supabaseHeaders(admin,token),'Content-Type':'application/json',Prefer:'return=representation'},body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(12000)});
 const value=await response.json().catch(()=>null);
 if(!response.ok){const code=value?.code||value?.error_code;if(code==='23505')throw new Failure(409,'This name or record is already in use.');if(response.status===429)throw new Failure(429,'Please wait before trying again.');if(String(value?.message).includes('rate_limit'))throw new Failure(429,'Please wait before posting again.');throw new Failure(response.status===401||response.status===403?401:400,'The request could not be completed. Please check your details.');}
 return value;
}
const service = (path:string, method='GET', body?:unknown) => upstream(path,secretKey(),method,body,true);
const rpc = (name:string, token:string, body:unknown) => upstream(`/rest/v1/rpc/${name}`,token,'POST',body);
function cookies(req:VercelRequest){return Object.fromEntries(String(req.headers.cookie||'').split(';').map(x=>{const i=x.indexOf('=');return i<0?['','']:[x.slice(0,i).trim(),decodeURIComponent(x.slice(i+1))]}))}
function setSession(res:VercelResponse,data:any){const secure=origin().startsWith('https:')?'; Secure':'';res.setHeader('Set-Cookie',[`ha_access=${encodeURIComponent(data.access_token)}; HttpOnly; SameSite=Lax; Path=/; Max-Age=${Math.min(Number(data.expires_in)||3600,3600)}${secure}`,`ha_refresh=${encodeURIComponent(data.refresh_token)}; HttpOnly; SameSite=Lax; Path=/; Max-Age=2592000${secure}`]);}
function clearSession(res:VercelResponse){res.setHeader('Set-Cookie',['ha_access=; HttpOnly; SameSite=Lax; Secure; Path=/; Max-Age=0','ha_refresh=; HttpOnly; SameSite=Lax; Secure; Path=/; Max-Age=0']);}
async function session(req:VercelRequest,res:VercelResponse,optional=false){
 let token=cookies(req).ha_access;let user:any;
 if(token){try{user=await upstream('/auth/v1/user',token)}catch{token=undefined as any}}
 if(!user&&cookies(req).ha_refresh){try{const fresh=await upstream('/auth/v1/token?grant_type=refresh_token',publicKey(),'POST',{refresh_token:cookies(req).ha_refresh});setSession(res,fresh);token=fresh.access_token;user=fresh.user}catch{clearSession(res)}}
 if(!user){if(optional)return null;throw new Failure(401,'Please sign in to continue.')}
 if(!user.email_confirmed_at)throw new Failure(403,'Please confirm your email address first.');
 if(!uuid(user.id))throw new Failure(401,'Please sign in to continue.');
 // Auth has already verified this JWT. Fetch only that user's role server-side;
 // member Data API privileges expose just public handles of published authors.
 const profiles=await service(`/rest/v1/profiles?id=eq.${user.id}&select=id,handle,role`);
 if(!profiles?.[0])throw new Failure(403,'Your profile is not ready. Please try again.');
 return {token,user,profile:profiles[0]};
}
function configuredReplyTo(){const value=process.env.EMAIL_REPLY_TO?.trim();if(!value)return undefined;if(!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value))throw new Failure(503,'Email replies are not configured.');return value}
async function mail(to:string,subject:string,content:string,unsubscribe?:string,idempotency?:string,language='en'){
 if(!mailReady())throw new Failure(503,'Email registration is not open yet.');
 const plain=content.replace(/<a[^>]+href="([^"]+)"[^>]*>(.*?)<\/a>/g,'$2 ($1)').replace(/<\/(p|h2|li)>/g,'\n\n').replace(/<br\s*\/?>/g,'\n').replace(/<[^>]*>/g,'').replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&quot;/g,'"').replace(/&#39;/g,"'");
 const replyTo=configuredReplyTo(),forum=localizedPath(language,'/forum'),privacy=localizedPath(language,'/privacy');
 const privateContactLabel:Record<string,string>={en:'Privacy & private contact',fr:'Confidentialité et demande privée',es:'Privacidad y contacto privado',ja:'プライバシーと非公開のお問い合わせ',zh:'隐私与私密联系'};
 const contactLabel=privateContactLabel[language]||privateContactLabel.en;
 const r=await fetch('https://api.resend.com/emails',{method:'POST',headers:{Authorization:`Bearer ${process.env.RESEND_API_KEY}`,'Content-Type':'application/json','User-Agent':'hyrule-atlas/1.0',...(idempotency?{'Idempotency-Key':idempotency}:{})},body:JSON.stringify({from:process.env.EMAIL_FROM,to:[to],subject,text:`Hyrule Atlas\n\n${plain}\n\nForum: ${forum}\n${contactLabel}: ${privacy}`,html:`<div style="font-family:Georgia,serif;max-width:600px;margin:auto;line-height:1.7;color:#16352e"><h1>Hyrule Atlas</h1>${content}<hr><p>Hyrule Atlas · Independent fan community · <a href="${forum}">Forum</a> · <a href="${privacy}">${contactLabel}</a></p></div>`,...(replyTo?{reply_to:replyTo}:{}),...(unsubscribe?{headers:{'List-Unsubscribe':`<${unsubscribe}>`,'List-Unsubscribe-Post':'List-Unsubscribe=One-Click'}}:{})}),signal:AbortSignal.timeout(12000)});
 if(!r.ok)throw new Failure(503,'The email could not be sent. Please try again later.');
 const result=await r.json().catch(()=>null);if(typeof result?.id!=='string'||!result.id.trim())throw new Failure(503,'The email provider did not confirm this message.');return result.id as string;
}
async function verifyHuman(token:unknown,action:string){
 if(!botProtectionReady())throw new Failure(503,'Registration is not open yet.');
 const response=await fetch('https://challenges.cloudflare.com/turnstile/v0/siteverify',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({secret:process.env.TURNSTILE_SECRET_KEY,response:text(token,10,2048)}),signal:AbortSignal.timeout(10000)});
 const result:any=await response.json();if(!result.success||result.action!==action||result.hostname!==new URL(origin()).hostname)throw new Failure(400,'Please complete the security check again.');
}
async function raw(req:VercelRequest,max=4300000){if(Buffer.isBuffer(req.body)||typeof req.body==='string'){const b=Buffer.from(req.body);if(b.length>max)throw new Failure(413,'This file is too large.');return b}const chunks:Buffer[]=[];let size=0;for await(const chunk of req){const b=Buffer.from(chunk);size+=b.length;if(size>max)throw new Failure(413,'This file is too large.');chunks.push(b)}return Buffer.concat(chunks)}
async function input(req:VercelRequest){if(req.body&&typeof req.body==='object'&&!Buffer.isBuffer(req.body)){if(JSON.stringify(req.body).length>50000)throw new Failure(413,'This request is too large.');return req.body}const data=await raw(req,50000);try{return JSON.parse(data.toString()||'{}')}catch{throw new Failure(400,'Invalid request.')}}
function publicThread(row:any){return {id:row.id,title:row.title,excerpt:row.body.slice(0,180),body:row.body,category:row.category,locale:row.locale,spoiler:row.spoiler,solved:Boolean(row.solution_post_id),replyCount:row.reply_count,author:{id:row.author_id,handle:row.author_handle},createdAt:row.created_at,lastActivityAt:row.last_activity_at}}
function publicArt(row:any){return {id:row.id,title:row.title,description:row.description,alt:row.alt_text,game:row.game,displayName:row.display_name,portfolioUrl:row.portfolio_url,imageUrl:`${origin()}/api/community?op=${row.status==='published'?'art-image':'art-preview'}&id=${row.id}`,createdAt:row.created_at,status:row.status,reviewReason:row.review_reason}}

export default async function handler(req:VercelRequest,res:VercelResponse){
 res.setHeader('Cache-Control','no-store');res.setHeader('X-Content-Type-Options','nosniff');res.setHeader('Referrer-Policy','no-referrer');res.setHeader('X-Robots-Tag','noindex, nofollow');
 try{
  const op=String(req.query.op||'status');const method=req.method||'GET';
  if(method==='POST'&&op!=='newsletter-unsubscribe'&&req.headers.origin!==origin())throw new Failure(403,'This request is not allowed.');
  if(!['GET','POST'].includes(method)){res.setHeader('Allow','GET, POST');throw new Failure(405,'Method not allowed.')}
  if(op==='status'&&method==='GET'){const s=databaseReady()?await session(req,res,true):null;return res.json({configured:databaseReady()&&mailReady()&&botProtectionReady(),turnstileSiteKey:process.env.TURNSTILE_SITE_KEY||'',user:s?{id:s.user.id,handle:s.profile.handle,emailVerified:true,role:s.profile.role}:null})}
  if(!databaseReady())throw new Failure(503,'The community is being prepared. Registration will open soon.');
  const anon=publicKey();
  if(op==='threads'&&method==='GET'){
   let query='/rest/v1/forum_threads_public?select=*&order=pinned.desc,last_activity_at.desc&limit=50';
   if(req.query.locale)query+=`&locale=eq.${locale(req.query.locale)}`;
   if(categories.includes(String(req.query.category)))query+=`&category=eq.${req.query.category}`;
   if(req.query.q){const q=text(req.query.q,1,80).replace(/[%_*(),]/g,'');query+=`&title=ilike.${encodeURIComponent('%'+q+'%')}`}
   const [rows,stats]=await Promise.all([upstream(query,anon),rpc('community_stats',anon,{})]);
   return res.json({threads:rows.map(publicThread),categories:categories.map(slug=>({slug,label:slug})),stats});
  }
  if(op==='thread'&&method==='GET'){
   if(!uuid(req.query.id))throw new Failure(400,'Invalid topic.');const rows=await upstream(`/rest/v1/forum_threads_public?id=eq.${req.query.id}`,anon);if(!rows.length)throw new Failure(404,'This topic is not available.');
   const posts=await upstream(`/rest/v1/forum_posts_public?thread_id=eq.${req.query.id}&order=created_at.asc&limit=200`,anon);
   return res.json({thread:publicThread(rows[0]),posts:posts.map((p:any)=>({id:p.id,body:p.body,author:{id:p.author_id,handle:p.author_handle},createdAt:p.created_at,spoiler:p.spoiler,isSolution:p.id===rows[0].solution_post_id}))});
  }
  if(op==='signup'&&method==='POST'){
   if(!mailReady())throw new Failure(503,'Registration is not open yet.');const b=await input(req);await verifyHuman(b.turnstileToken,'signup');if(!consent(b.termsAccepted))throw new Failure(400,'Please accept the community rules.');
   const handle=text(b.handle,3,24);if(!/^[\p{L}\p{N}_-]+$/u.test(handle)||/^(admin|nintendo|hyruleatlas|moderator|support)$/i.test(handle))throw new Failure(400,'Please choose another public name.');
   await upstream('/auth/v1/signup',anon,'POST',{email:email(b.email),password:password(b.password),data:{handle,locale:locale(b.locale),terms_version:'2026-10-11'},email_redirect_to:`${origin()}/forum`});
   return res.json({verificationSent:true});
  }
  if(op==='login'&&method==='POST'){const b=await input(req);await verifyHuman(b.turnstileToken,'login');const data=await upstream('/auth/v1/token?grant_type=password',anon,'POST',{email:email(b.email),password:password(b.password)});if(!data.user.email_confirmed_at)throw new Failure(403,'Please confirm your email address first.');setSession(res,data);return res.json({signedIn:true})}
  if(op==='logout'&&method==='POST'){const s=await session(req,res,true);if(s)await upstream('/auth/v1/logout',s.token,'POST',{}).catch(()=>null);clearSession(res);return res.json({signedOut:true})}
  if(op==='reset-password'&&method==='POST'){const b=await input(req);await verifyHuman(b.turnstileToken,'reset');await upstream('/auth/v1/recover',anon,'POST',{email:email(b.email),redirect_to:`${origin()}/forum?reset=1`}).catch(()=>null);return res.json({sent:true})}
  if(op==='confirm'){
   const type=String(req.query.type),lang=locale(req.query.locale),copy=emailCopy[lang];if(!['signup','recovery','email'].includes(type))throw new Failure(400,'Invalid confirmation link.');const tokenHash=text(req.query.token_hash,20,256);
   if(method==='GET')return confirmationPage(res,`?op=confirm&type=${type}&locale=${lang}&token_hash=${encodeURIComponent(tokenHash)}`,copy.account,copy.continue,lang);
   const data=await upstream('/auth/v1/verify',anon,'POST',{type,token_hash:tokenHash});setSession(res,data);return res.redirect(303,`${localizedPath(lang,'/forum')}?${type==='recovery'?'reset=1':'verified=1'}`);
  }
  if(op==='newsletter-subscribe'&&method==='POST'){
   const b=await input(req);await verifyHuman(b.turnstileToken,'newsletter');if(!consent(b.consent))throw new Failure(400,'Please confirm you want to receive the weekly newsletter.');if(!mailReady())throw new Failure(503,'Newsletter registration is not open yet.');
   const address=email(b.email),token=randomBytes(32).toString('hex');const record=await service('/rest/v1/rpc/request_newsletter','POST',{p_email:address,p_locale:locale(b.locale),p_token_hash:hash(token)});
   if(record?.send){const lang=locale(b.locale),copy=emailCopy[lang],link=`${origin()}/api/community?op=newsletter-confirm&locale=${lang}&token=${token}`;try{await mail(address,copy.subject,`<p>${copy.intro}</p><p><a href="${link}">${copy.confirm}</a></p><p>${copy.ignore}</p>`,undefined,undefined,lang)}catch(error){await service('/rest/v1/rpc/mark_newsletter_confirmation_failed','POST',{p_email:address,p_token_hash:hash(token)}).catch(()=>null);throw error}}
   return res.json({accepted:true});
  }
  if(op==='newsletter-confirm'){const token=text(req.query.token,64,64),lang=locale(req.query.locale),copy=emailCopy[lang];if(!/^[0-9a-f]{64}$/.test(token))throw new Failure(400,'Invalid confirmation link.');if(method==='GET')return confirmationPage(res,`?op=newsletter-confirm&locale=${lang}&token=${token}`,copy.subscribe,copy.confirm,lang);const result=await service('/rest/v1/rpc/confirm_newsletter','POST',{p_token_hash:hash(token)});if(!result)throw new Failure(400,'This confirmation link has expired.');return res.redirect(303,`${localizedPath(lang,'/newsletter')}?confirmed=1`)}
  if(op==='contact'&&method==='POST'){const b=await input(req);await verifyHuman(b.turnstileToken,'contact');await service('/rest/v1/rpc/submit_private_request','POST',{p_email:email(b.email),p_reason:text(b.reason,20,3000)});return res.json({accepted:true})}
  if(op==='newsletter-unsubscribe'){
   if(!uuid(req.query.id))throw new Failure(400,'Invalid unsubscribe link.');const token=text(req.query.token,64,64);if(!/^[0-9a-f]{64}$/.test(token)||!timingSafeEqual(Buffer.from(token,'hex'),Buffer.from(unsubscribeToken(String(req.query.id)),'hex')))throw new Failure(400,'Invalid unsubscribe link.');
   const lang=locale(req.query.locale),copy=emailCopy[lang];if(method==='GET')return confirmationPage(res,`?op=newsletter-unsubscribe&id=${req.query.id}&locale=${lang}&token=${token}`,copy.unsubscribe+' · Hyrule Atlas',copy.unsubscribe,lang);
   await service('/rest/v1/newsletter_subscribers?id=eq.'+req.query.id,'PATCH',{status:'unsubscribed',unsubscribed_at:new Date().toISOString()});return res.status(200).send(copy.cancelled);
  }
  if(op==='fan-art'&&method==='GET'){const rows=await upstream('/rest/v1/fan_art_public?order=created_at.desc&limit=60',anon);return res.json({artworks:rows.map(publicArt)})}
  if(op==='art-image'&&method==='GET'){
   if(!uuid(req.query.id))throw new Failure(400,'Invalid artwork.');const rows=await service(`/rest/v1/fan_art?id=eq.${req.query.id}&status=eq.published&select=image_key`);if(!rows.length)throw new Failure(404,'This artwork is not available.');
   const r=await fetch(`${process.env.SUPABASE_URL}/storage/v1/object/fanart-private/${rows[0].image_key}`,{headers:supabaseHeaders(true),signal:AbortSignal.timeout(12000)});if(!r.ok)throw new Failure(404,'This artwork is not available.');res.setHeader('Content-Type','image/webp');return res.send(Buffer.from(await r.arrayBuffer()));
  }
  const s=await session(req,res);const b=method==='POST'&&op!=='fan-art-submit'?await input(req):{};
  if(op==='art-preview'&&method==='GET'){
   if(!uuid(req.query.id))throw new Failure(400,'Invalid artwork.');const rows=await service(`/rest/v1/fan_art?id=eq.${req.query.id}&status=neq.withdrawn${s!.profile.role==='admin'?'':`&author_id=eq.${s!.user.id}`}&select=image_key`);if(!rows.length)throw new Failure(404,'This artwork is not available.');const r=await fetch(`${process.env.SUPABASE_URL}/storage/v1/object/fanart-private/${rows[0].image_key}`,{headers:supabaseHeaders(true),signal:AbortSignal.timeout(12000)});if(!r.ok)throw new Failure(404,'This artwork is not available.');res.setHeader('Content-Type','image/webp');return res.send(Buffer.from(await r.arrayBuffer()));
  }
  if(op==='thread'&&method==='POST'){if(!categories.includes(b.category))throw new Failure(400,'Please choose a category.');const id=await rpc('create_forum_thread',s!.token,{p_title:text(b.title,8,140),p_body:cleanBody(b.body),p_category:b.category,p_locale:locale(b.locale),p_spoiler:consent(b.spoiler)});return res.json({id,pending:true})}
  if(op==='reply'&&method==='POST'){if(!uuid(b.threadId))throw new Failure(400,'Invalid topic.');const id=await rpc('create_forum_reply',s!.token,{p_thread_id:b.threadId,p_body:cleanBody(b.body),p_spoiler:consent(b.spoiler)});return res.json({id,pending:true})}
  if(op==='mark-solution'&&method==='POST'){if(!uuid(b.threadId)||!uuid(b.postId))throw new Failure(400,'Invalid reply.');await rpc('mark_forum_solution',s!.token,{p_thread_id:b.threadId,p_post_id:b.postId});return res.json({saved:true})}
  if(op==='report'&&method==='POST'){if(!['thread','post','fan-art'].includes(b.targetType)||!uuid(b.targetId))throw new Failure(400,'Invalid report.');await rpc('submit_community_report',s!.token,{p_target_type:b.targetType,p_target_id:b.targetId,p_reason:text(b.reason,10,1000)});return res.json({received:true})}
  if(op==='change-password'&&method==='POST'){await upstream('/auth/v1/user',s!.token,'PUT',{password:password(b.password)});return res.json({saved:true})}
  if(op==='delete-account'&&method==='POST'){
   await upstream('/auth/v1/token?grant_type=password',anon,'POST',{email:s!.user.email,password:password(b.password)});
   const arts=await service(`/rest/v1/fan_art?author_id=eq.${s!.user.id}&select=image_key`);
   await removeArtImages(arts.map((a:any)=>a.image_key));
   await service(`/rest/v1/newsletter_subscribers?email=eq.${encodeURIComponent(s!.user.email)}`,'DELETE');
   await service(`/auth/v1/admin/users/${s!.user.id}`,'DELETE');clearSession(res);return res.json({deleted:true});
  }
  if(op==='my-fan-art'&&method==='GET'){const rows=await upstream(`/rest/v1/fan_art?author_id=eq.${s!.user.id}&order=created_at.desc`,s!.token);return res.json({artworks:rows.map(publicArt)})}
  if(op==='fan-art-withdraw'&&method==='POST'){if(!uuid(b.id))throw new Failure(400,'Invalid artwork.');await rpc('withdraw_fan_art',s!.token,{p_id:b.id});const rows=await service(`/rest/v1/fan_art?id=eq.${b.id}&author_id=eq.${s!.user.id}&select=image_key`);await removeArtImages(rows.map((a:any)=>a.image_key));await service(`/rest/v1/fan_art?id=eq.${b.id}`,'PATCH',{image_purged_at:new Date().toISOString()});return res.json({withdrawn:true})}
  if(op==='fan-art-submit'&&method==='POST'){
   const buffer=await raw(req);const form=await new Request('https://upload.invalid',{method:'POST',headers:{'Content-Type':String(req.headers['content-type'])},body:buffer}).formData();
   for(const key of ['sitePermission','authorDeclaration','rightsUnderstanding'])if(!consent(form.get(key)))throw new Failure(400,'Please confirm the artwork permissions.');
   const file:any=form.get('file');if(!file||typeof file.arrayBuffer!=='function'||file.size>3*1024*1024||!['image/png','image/jpeg','image/webp'].includes(file.type))throw new Failure(400,'Choose a JPG, PNG or WebP image up to 3 MB.');
   const decoded=sharp(Buffer.from(await file.arrayBuffer()),{limitInputPixels:12000000,animated:false});const meta=await decoded.metadata();if(!['png','jpeg','webp'].includes(meta.format!)||!meta.width||!meta.height||meta.width<100||meta.height<100)throw new Failure(400,'This image format or size is not supported.');
   const webp=await decoded.rotate().resize({width:1800,height:1800,fit:'inside',withoutEnlargement:true}).webp({quality:88}).toBuffer();const key=`${s!.user.id}/${randomBytes(16).toString('hex')}.webp`;
   const upload=await fetch(`${process.env.SUPABASE_URL}/storage/v1/object/fanart-private/${key}`,{method:'POST',headers:{...supabaseHeaders(true),'Content-Type':'image/webp'},body:Uint8Array.from(webp),signal:AbortSignal.timeout(12000)});if(!upload.ok)throw new Failure(503,'The image could not be stored.');
   try{const id=await service('/rest/v1/rpc/submit_fan_art','POST',{p_author_id:s!.user.id,p_title:text(form.get('title'),3,100),p_description:text(form.get('description'),10,2000),p_alt:text(form.get('alt'),10,300),p_game:text(form.get('game'),1,80),p_display_name:text(form.get('displayName'),2,60),p_portfolio:safeUrl(form.get('portfolioUrl')),p_key:key,p_newsletter:consent(form.get('newsletterPermission')),p_site_permission:consent(form.get('sitePermission')),p_author_declaration:consent(form.get('authorDeclaration')),p_rights_understanding:consent(form.get('rightsUnderstanding'))});return res.json({id,pending:true})}catch(error){await removeArtImages([key]);throw error}
  }
  if(s!.profile.role!=='admin')throw new Failure(403,'This action is reserved for the community team.');
  if(op==='fan-art-purge'&&method==='POST'){if(!uuid(b.id))throw new Failure(400,'Invalid artwork.');const rows=await service(`/rest/v1/fan_art?id=eq.${b.id}&status=eq.withdrawn&select=image_key`);if(!rows.length)throw new Failure(404,'This withdrawn artwork is not available.');await removeArtImages(rows.map((a:any)=>a.image_key));await service(`/rest/v1/fan_art?id=eq.${b.id}`,'PATCH',{image_purged_at:new Date().toISOString()});return res.json({saved:true})}
  if(op==='admin-queue'&&method==='GET'){const [threads,posts,artworks,reports,issues,requests,artCleanup]=await Promise.all([service('/rest/v1/forum_threads?status=eq.pending&order=created_at.asc&limit=100'),service('/rest/v1/forum_posts?status=eq.pending&order=created_at.asc&limit=100'),service('/rest/v1/fan_art?status=eq.pending&order=created_at.asc&limit=60'),service('/rest/v1/community_reports?status=eq.open&order=created_at.asc&limit=100'),service('/rest/v1/newsletter_issues?order=created_at.desc&limit=12'),service('/rest/v1/private_requests?status=eq.open&order=created_at.asc&limit=100'),service('/rest/v1/fan_art?status=eq.withdrawn&image_purged_at=is.null&select=id,title,image_purged_at&limit=100')]);return res.json({threads,posts,artworks,reports,issues,requests,artCleanup})}
  if(op==='resolve-request'&&method==='POST'){if(!uuid(b.id)||!['report','private'].includes(b.type))throw new Failure(400,'Invalid request.');await service(`/rest/v1/${b.type==='report'?'community_reports':'private_requests'}?id=eq.${b.id}`,'PATCH',{status:'resolved'});return res.json({saved:true})}
  if(op==='moderate'&&method==='POST'){if(!uuid(b.id)||!['thread','post','fan-art'].includes(b.type)||!['published','rejected','hidden'].includes(b.status))throw new Failure(400,'Invalid moderation action.');await rpc('moderate_community',s!.token,{p_type:b.type,p_id:b.id,p_status:b.status,p_reason:text(b.reason||'Reviewed by the community team.',1,1000)});return res.json({saved:true})}
  if(op==='newsletter-import'&&method==='POST'){
   if(b.qaReport?.passed!==true||b.qaReport?.humanReviewRequired!==true||!Array.isArray(b.sources)||!b.sources.length||b.sources.length>30)throw new Failure(400,'Only a draft with a passing review and recorded sources can enter the editorial queue.');
   if(!languages.includes(String(b.locale)))throw new Failure(400,'Choose a supported newsletter language.');
   const sources=b.sources.map((x:any)=>{const url=safeUrl(x.url),checkedAt=text(x.checkedAt,10,40);if(!url||!Number.isFinite(Date.parse(checkedAt)))throw new Failure(400,'Each source needs a valid HTTPS link and verification date.');return {title:text(x.title,3,200),url,checkedAt}});
   const subject=text(b.subject,5,150),body=text(b.body,100,20000),language=String(b.locale);
   if(/[\u0000-\u001F\u007F]/.test(subject))throw new Failure(400,'The newsletter subject must be one line.');
   const edition=text(b.qaReport.issue,6,100);if(!/^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(edition))throw new Failure(400,'The reviewed draft needs a stable edition identifier.');
   const issueKey=hash(JSON.stringify([language,edition]));
   const existing=await service(`/rest/v1/newsletter_issues?issue_key=eq.${issueKey}&select=id,subject,body`);
   if(existing.length){if(existing[0].subject!==subject||existing[0].body!==body)throw new Failure(409,'This edition is already imported. Edit its existing draft instead.');return res.json({id:existing[0].id,reused:true})}
   try{const rows=await service('/rest/v1/newsletter_issues','POST',{issue_key:issueKey,subject,body,locale:language,sources,qa_report:b.qaReport,status:'ready_for_max'});return res.json({id:rows[0].id,reused:false})}
   catch(error){if(!(error instanceof Failure)||error.status!==409)throw error;const rows=await service(`/rest/v1/newsletter_issues?issue_key=eq.${issueKey}&select=id,subject,body`);if(!rows.length)throw error;if(rows[0].subject!==subject||rows[0].body!==body)throw new Failure(409,'This edition is already imported. Edit its existing draft instead.');return res.json({id:rows[0].id,reused:true})}
  }
  if(op==='newsletter-review'&&method==='POST'){if(!uuid(b.id))throw new Failure(400,'Invalid newsletter.');const rows=await service(`/rest/v1/newsletter_issues?id=eq.${b.id}`);const issue=rows[0];if(!issue||!['ready_for_max','reviewed'].includes(issue.status)||!issue.qa_report?.passed)throw new Failure(400,'This draft has not passed its review.');const reviewedSubject=text(b.subject,5,150);if(/[\u0000-\u001F\u007F]/.test(reviewedSubject))throw new Failure(400,'The newsletter subject must be one line.');const revision=issue.reviewed_at?`eq.${encodeURIComponent(issue.reviewed_at)}`:'is.null';const saved=await service(`/rest/v1/newsletter_issues?id=eq.${b.id}&status=eq.${issue.status}&reviewed_at=${revision}`,'PATCH',{subject:reviewedSubject,body:text(b.body,100,20000),status:'reviewed',reviewed_by:s!.user.id,reviewed_at:new Date().toISOString()});if(!Array.isArray(saved)||!saved.length)throw new Failure(409,'This edition changed while you reviewed it. Reload the current draft.');return res.json({saved:true})}
  if(op==='newsletter-send'&&method==='POST'){
   if(!uuid(b.id)||b.confirmed!==true)throw new Failure(400,'Explicit approval of this newsletter is required.');const rows=await service(`/rest/v1/newsletter_issues?id=eq.${b.id}`);const issue=rows[0];if(issue?.status==='blocked')throw new Failure(409,'This delivery requires manual review before another attempt.');if(!issue||!['reviewed','sending'].includes(issue.status)||!issue.reviewed_at||!issue.qa_report?.passed)throw new Failure(400,'Review this newsletter before sending it.');
   if(issue.subject!==b.expectedSubject||issue.body!==b.expectedBody)throw new Failure(409,'This edition changed after your approval. Review the current text before sending.');
   if(issue.status==='reviewed'){const locked=await service(`/rest/v1/newsletter_issues?id=eq.${issue.id}&status=eq.reviewed&reviewed_at=eq.${encodeURIComponent(issue.reviewed_at)}`,'PATCH',{status:'sending'});if(!Array.isArray(locked)||!locked.length)throw new Failure(409,'This edition changed while sending began. Review its current state.')}
   const recipients=await service('/rest/v1/rpc/reserve_newsletter_batch','POST',{p_issue_id:issue.id,p_locale:issue.locale});
   if(!recipients.length){const latest=await service(`/rest/v1/newsletter_issues?id=eq.${issue.id}&select=status`);if(latest[0]?.status==='blocked')throw new Failure(409,'This delivery requires manual review before another attempt.')}
   const html=newsletterHtml(issue.body,issue.sources,issue.locale);const deliveries=await Promise.allSettled(recipients.map(async(recipient:any)=>{const link=`${origin()}/api/community?op=newsletter-unsubscribe&id=${recipient.id}&locale=${issue.locale}&token=${unsubscribeToken(recipient.id)}`;let providerId:string|undefined;try{providerId=await mail(recipient.email,issue.subject,html+`<p><a href="${link}">${emailCopy[issue.locale].unsubscribe}</a></p>`,link,`hyrule-${issue.id}-${recipient.id}`,issue.locale);await service(`/rest/v1/newsletter_deliveries?issue_id=eq.${issue.id}&subscriber_id=eq.${recipient.id}`,'PATCH',{state:'sent',provider_message_id:providerId,updated_at:new Date().toISOString()})}catch(error){const state=providerId?'needs_review':'failed';await service(`/rest/v1/newsletter_deliveries?issue_id=eq.${issue.id}&subscriber_id=eq.${recipient.id}`,'PATCH',{state,provider_message_id:providerId||null,updated_at:new Date().toISOString()}).catch(()=>null);if(providerId)await service(`/rest/v1/newsletter_issues?id=eq.${issue.id}`,'PATCH',{status:'blocked'}).catch(()=>null);throw error}}));
   const failure=deliveries.find(result=>result.status==='rejected');if(failure?.status==='rejected')throw failure.reason;
   const remaining=Number(await service('/rest/v1/rpc/newsletter_remaining','POST',{p_issue_id:issue.id,p_locale:issue.locale}));if(remaining===0)await service(`/rest/v1/newsletter_issues?id=eq.${issue.id}`,'PATCH',{status:'sent',sent_at:new Date().toISOString()});return res.json({sent:recipients.length,remaining,paused:recipients.length===0&&remaining>0});
  }
  throw new Failure(404,'This action is not available.');
 }catch(error){const status=error instanceof Failure?error.status:500;return res.status(status).json({error:error instanceof Failure?error.message:'The service could not complete this request. Please try again later.'})}
}
