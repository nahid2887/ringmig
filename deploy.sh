#!/bin/bash
cd /root/ringmig
git pull
docker-compose down
docker-compose up -d
sleep 5
docker-compose exec -T web python manage.py migrate
docker-compose exec -T web python manage.py compilemessages
echo "Multi-language support deployed successfully!"
