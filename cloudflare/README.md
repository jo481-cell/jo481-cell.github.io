# Hyrule Atlas sur Cloudflare

La branche `migration/cloudflare-pages` réunit le site exporté et les sources Cloudflare.
GitHub Pages historique publie le dossier racine de `main` avec `.nojekyll`.
Garder cet hébergement sur sa branche de fichiers publics. Pour reprendre un nouvel
export, intégrer `origin/main` **dans la branche de migration**, puis reconstruire.
Une fusion en sens inverse rendrait les outils et les fixtures accessibles sur
l’hébergement historique. Seul le dossier `cloudflare/pages/dist` est destiné au
service statique Cloudflare. Le Worker et les Pages Functions se déploient séparément.
Le `vercel.json` de cette branche désactive son déploiement Git automatique vers
Vercel. Le fichier `.vercelignore` écarte le répertoire `cloudflare/` des envois CLI.

## Construire et tester

Depuis la racine du dépôt avec Python 3.12+ et Node 22.12+ :

```powershell
python cloudflare/build-pages.py
npm ci --prefix cloudflare/api
npm --prefix cloudflare/api test
npm --prefix cloudflare/api run check
node --test cloudflare/pages/verify-binding.mjs
```

Le générateur lit les objets du commit Git courant, y compris les anciens actifs
encore référencés par les navigateurs. Le sitemap sélectionne les pages publiques.
La liste complémentaire couvre le forum, la recherche et les autres routes publiques
volontairement hors sitemap. Un nouveau format de média ou une nouvelle route hors
sitemap demande une mise à jour de cette liste. Les fichiers de configuration,
les sources du Worker et les tests restent hors de la distribution.

Pour le test local du frontal, ouvrir un terminal dans `cloudflare/api` et lancer
`npm run dev`. Dans un second terminal, depuis `cloudflare/pages`, lancer
`../api/node_modules/.bin/wrangler pages dev dist --port 8789`.
Le serveur local applique la politique de prévisualisation. En test d’intégration,
configurer le Worker avec des services de test et transmettre au serveur local
l’en-tête HTTP `Host: hyruleatlas.com` pour exercer le routage de production.
Les tests automatisés du Worker utilisent leurs propres fixtures.

## Publication et vérification

1. Consulter [la configuration du Worker](api/README.md). Garder les secrets
   existants dans les secrets Cloudflare et préserver la clé des liens de
   désabonnement. Déployer le service privé `hyrule-atlas-community` depuis
   `cloudflare/api` avec `npx --no-install wrangler deploy`.
2. Vérifier le nom du projet Pages et sa branche de production. Le nom prévu est
   `hyrule-atlas` et son hôte stable est `hyrule-atlas.pages.dev`. En cas de
   changement de nom, ajuster les deux valeurs dans `pages/wrangler.toml`.
   Depuis `cloudflare/pages`, utiliser
   `../api/node_modules/.bin/wrangler pages deploy dist --project-name hyrule-atlas --branch main`
   **si la branche de production configurée sur Pages est `main`**. Pour une autre
   branche de production Pages, donner son nom à `--branch`. Ce paramètre sélectionne
   l’environnement de déploiement Pages. Il n’effectue aucun push Git.
3. Vérifier sur l’hôte stable un guide, ses traductions, la 404, les redirections
   de jeux et de contact, le cache et l’en-tête `X-Robots-Tag`. Le GET anonyme
   `/api/community?op=status` renvoie l’en-tête `X-Hyrule-Community: reached`
   lorsque le Worker répond avec un statut de configuration valide. Avant la
   saisie des secrets, la réponse attendue est 503 et `{"configured":false}`.
   Après leur saisie, elle passe à 200 et `{"configured":true}`. Sans cet en-tête,
   une réponse 503 ne permet pas de confirmer que le Worker a été atteint.
   Les sondes `/api/community?probe=threads` et `/api/community?probe=fan-art`
   vérifient les lectures anonymes du forum francophone et de la galerie. Elles
   renvoient 204 après lecture réussie ou 503 en cas d’indisponibilité, avec un
   corps vide et sans cookie. Toute écriture reste bloquée. Pour vérifier à la
   fois l’alias stable et l’URL immuable du déploiement, installer le module
   Python `requests`, puis exécuter depuis la racine :

   ```powershell
   python cloudflare/verify/pages-live.py --deployment <empreinte>.hyrule-atlas.pages.dev --api-only --expect-configured
   ```

   Retirer `--expect-configured` pour vérifier l’état initial, avant les secrets,
   ou `--api-only` pour inclure le sitemap, les redirections et les ressources.
   Le reçu local est écrit dans `cloudflare/verify/checks/`. Valider les parcours
   avec écriture dans un environnement
   dédié disposant d’une base et d’un transport de courriels de test.
4. Une fois la bascule autorisée, conserver le domaine canonique `hyruleatlas.com`
   et ajouter la [règle de redirection www](pages/www-redirect-rule.json) aux règles
   existantes de redirection de zone, en conservant chemins et paramètres.
   L’exception `/.well-known/` permet la validation des certificats TLS. Garder
   les enregistrements DNS du courrier et les autres règles de la zone. L’export
   inclut déjà sa balise Web Analytics ; laisser l’injection automatique de Pages
   désactivée afin de conserver un seul collecteur.
5. Sur le domaine canonique, vérifier l’API avec
   `node cloudflare/verify/community-smoke.mjs https://hyruleatlas.com`, les redirections
   de `www`, l’absence de `noindex` sur les guides et l’indexation interdite sur les
   alias. `python cloudflare/verify/post-cutover.py` contrôle ces redirections,
   les fichiers servis, le cache, les en-têtes et la 404. Garder le déploiement
   précédent accessible pour la réversibilité.

## Préparation AdSense

Après validation des droits sur les contenus du site, récupérer dans AdSense la
référence de l’éditeur pour `hyruleatlas.com`. Construire avec
`python cloudflare/build-pages.py --adsense-publisher-id <référence-ca-pub>` pour
insérer la balise de vérification dans l’en-tête de l’accueil. Ajouter
`--adsense-ads-txt` pour générer aussi l’enregistrement Google recommandé dans
`/ads.txt`. Ces paramètres publient des métadonnées de vérification. Un build
sans option conserve l’export d’origine.

Après publication, vérifier la balise sur `https://hyruleatlas.com/` et, le cas
échéant, la référence inscrite dans `/ads.txt`. Valider la propriété dans
AdSense, puis demander l’examen. La diffusion des annonces constitue une étape
distincte après le statut « Prêt ». Elle demande une mise à jour de la politique
de confidentialité, de la politique de sécurité du contenu et du mécanisme de
consentement pour les régions concernées. [Procédure de Google](https://support.google.com/adsense/answer/12169212?hl=fr)
