# API communautaire Hyrule Atlas

Le Worker `hyrule-atlas-community` reçoit les requêtes sur `/api/community` et
`/api/community/`. Il conserve les paramètres `op`, les cookies de session,
les liens de confirmation existants, les appels RPC et le stockage privé Supabase
du site. La référence de portage est [l’API publiée au commit f10f57d](https://github.com/jo481-cell/jo481-cell.github.io/blob/f10f57d680a235e7e0f60caf68834fb1427db05e/api/community.ts).

## Raccordement à Pages

La configuration Pages doit associer `COMMUNITY` au service `hyrule-atlas-community`.
La fonction Pages qui reçoit la requête transmet l’URL initiale, les en-têtes,
les cookies, le corps et la réponse par `return context.env.COMMUNITY.fetch(context.request)`.
Le Worker déclare son propre binding Images nommé `IMAGES`. Son fichier Wrangler
désactive l’adresse publique workers.dev et les URL publiques de prévisualisation.

## Configuration

| Variable ou binding | Utilisation |
| --- | --- |
| `PUBLIC_SITE_ORIGIN` | Origine exacte du navigateur, sans barre finale. Défaut de production `https://hyruleatlas.com`. Sert au contrôle des POST et aux liens par courriel. |
| `SUPABASE_URL` | URL du projet Supabase déjà utilisé par le site. |
| `SUPABASE_PUBLISHABLE_KEY` ou `SUPABASE_ANON_KEY` | Clé publique actuelle ou ancienne clé anonyme. |
| `SUPABASE_SECRET_KEY` ou `SUPABASE_SERVICE_ROLE_KEY` | Secret serveur pour les opérations communautaires autorisées. |
| `TURNSTILE_SITE_KEY` et `TURNSTILE_SECRET_KEY` | Site public et secret de vérification associés au domaine du formulaire. |
| `RESEND_API_KEY` et `EMAIL_FROM` | Clé Resend d’envoi limitée à `lettres.hyruleatlas.com` et expéditeur `Hyrule Atlas <infolettre@lettres.hyruleatlas.com>`. Les courriels de compte utilisent le SMTP configuré dans Supabase. |
| `EMAIL_REPLY_TO` | Adresse de réponse facultative. |
| `NEWSLETTER_TOKEN_SECRET` | Secret HMAC existant de 32 caractères minimum. Réutiliser sa valeur actuelle pour préserver la validité des anciens liens de désabonnement. |
| `IMAGES` | Binding Images Worker défini dans `wrangler.jsonc`. |

Utiliser les secrets du Worker pour les clés privées. Pour un essai de formulaire
sur un autre hôte, l’origine et le site Turnstile doivent correspondre à l’hôte
d’essai. Les tests inclus injectent leurs propres valeurs fictives et interceptent
toutes les requêtes externes.

## Essai local

Depuis ce dossier avec Node 22.12 ou une version plus récente compatible avec Wrangler, exécuter
`npm ci`, puis `npm test`. Le test démarre workerd et utilise le binding Images local
pour convertir un vrai PNG. La validation des courriels et des opérations de stockage
s’appuie sur des services simulés. `npm run check` vérifie la construction du bundle.

`npm run dev` démarre le Worker seul. `GET /api/community?op=status` répond avec
`configured: false` quand les paramètres communautaires sont absents. Pour une
répétition locale avec Pages, démarrer également Pages sur un autre port et lui
transmettre le service par son binding Wrangler.

## Points de contrôle en environnement hébergé

- La conversion accepte les PNG, JPEG et WebP jusqu’à 3 Mio et 12 millions de pixels.
  Elle produit un WebP fixe à qualité 88, plafonné à 1 800 px de chaque côté,
  sans agrandissement. L’API retire les blocs EXIF et XMP du résultat avant
  stockage et rejette un fichier réencodé qui dépasse les 3 Mio du bucket.
  Vérifier l’orientation et la suppression des métadonnées sur Images hébergé.
- Les courriels gardent les vérifications de consentement, le lien signé et
  l’approbation humaine de chaque édition. Le plafond de cinq destinataires par lot
  réside dans la fonction SQL Supabase existante. La recette hébergée doit mesurer
  le temps CPU du Worker Free sur un lot représentatif.
- Les cookies utilisent `HttpOnly`, `SameSite=Lax` et, sur HTTPS, `Secure`.
  Le retour d’authentification et les deux en-têtes `Set-Cookie` doivent traverser Pages.
