#!/bin/bash
set -euo pipefail

cd /root/ringmig
git pull

if docker compose version >/dev/null 2>&1; then
	DC="docker compose"
else
	DC="docker-compose"
fi

# Clean old service/container metadata that can trigger ContainerConfig KeyError in compose v1.
$DC down --remove-orphans || true
$DC rm -f web || true
docker rm -f ringmig_web >/dev/null 2>&1 || true

$DC up -d --build
sleep 5
$DC exec -T web python manage.py migrate
$DC exec -T web python manage.py compilemessages
echo "Multi-language support deployed successfully!"
