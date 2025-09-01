docker compose pull
docker compose up -d --build

/optional   docker compose build assistant
/optional    docker compose push assistant

# make sure .gitattributes is staged
git add .gitattributes

# renormalize all tracked files to LF per .gitattributes
git add --renormalize .

git commit -m "Add .gitattributes and normalize line endings"
git push origin main





docker compose logs -f traefik
docker compose logs -f assistant
