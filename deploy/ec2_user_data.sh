#!/bin/bash
# Instalación del SGR en una instancia EC2 Ubuntu 24.04 (capa gratuita / AWS Academy).
#
# Se entrega como "user data" al lanzar la instancia. Instala PostgreSQL,
# Gunicorn y Nginx con HTTPS (certificado autofirmado, ya que el prototipo no
# tiene dominio propio) y deja el SGR funcionando con datos ficticios.
#
# Todo queda registrado en /var/log/sgr-instalacion.log
set -euo pipefail
exec > /var/log/sgr-instalacion.log 2>&1

REPO="https://github.com/Mauv8/SGR-Ing-Software.git"
APP=/opt/sgr

apt-get update -y
apt-get install -y python3-venv python3-pip postgresql nginx git openssl

# --- Base de datos: usuario y clave aleatoria, sólo accesible localmente ---
CLAVE_BD=$(openssl rand -hex 24)
sudo -u postgres psql -c "CREATE USER sgr WITH PASSWORD '${CLAVE_BD}';"
sudo -u postgres psql -c "CREATE DATABASE sgr OWNER sgr;"

# --- Código y entorno virtual ---
useradd --system --home "$APP" --shell /usr/sbin/nologin sgr || true
git clone "$REPO" "$APP"
python3 -m venv "$APP/.venv"
"$APP/.venv/bin/pip" install -r "$APP/requirements.txt" gunicorn

# Archivo de entorno base (sin la IP: la escribe sgr-ip.sh en cada arranque).
cat > "$APP/.env" <<ENV
DJANGO_SECRET_KEY=$(openssl rand -base64 48 | tr -d '\n=/+')
DJANGO_DEBUG=False
DJANGO_DETRAS_DE_PROXY=True
POSTGRES_DB=sgr
POSTGRES_USER=sgr
POSTGRES_PASSWORD=${CLAVE_BD}
POSTGRES_HOST=localhost
POSTGRES_SSLMODE=prefer
ENV

# --- IP en cada arranque -----------------------------------------------------
# En AWS Academy la IP pública cambia al reiniciar el laboratorio. Este script
# corre antes de la aplicación en cada encendido: actualiza ALLOWED_HOSTS y
# CSRF con la IP actual y regenera el certificado si la IP cambió.
cat > /usr/local/bin/sgr-ip.sh <<'IPSCRIPT'
#!/bin/bash
set -e
ENVF=/opt/sgr/.env
TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 300")
IP=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/public-ipv4)
sed -i '/^DJANGO_ALLOWED_HOSTS=/d;/^DJANGO_CSRF_TRUSTED_ORIGINS=/d' "$ENVF"
echo "DJANGO_ALLOWED_HOSTS=${IP}" >> "$ENVF"
echo "DJANGO_CSRF_TRUSTED_ORIGINS=https://${IP}" >> "$ENVF"
if ! openssl x509 -in /etc/ssl/certs/sgr.crt -noout -subject 2>/dev/null | grep -q "CN *= *${IP}$"; then
  openssl req -x509 -nodes -days 30 -newkey rsa:2048 \
    -keyout /etc/ssl/private/sgr.key -out /etc/ssl/certs/sgr.crt -subj "/CN=${IP}"
fi
echo "SGR: IP ${IP}"
IPSCRIPT
chmod 755 /usr/local/bin/sgr-ip.sh
cat > /etc/systemd/system/sgr-ip.service <<UNIT
[Unit]
Description=SGR: actualizar IP publica antes de iniciar
After=network-online.target
Wants=network-online.target
Before=sgr.service nginx.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/sgr-ip.sh

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable sgr-ip.service
/usr/local/bin/sgr-ip.sh

chmod 600 "$APP/.env"
chown -R sgr:sgr "$APP"

cd "$APP"
sudo -u sgr bash -c "set -a; . ./.env; set +a; .venv/bin/python manage.py migrate --noinput && \
  .venv/bin/python manage.py collectstatic --noinput && .venv/bin/python manage.py cargar_datos_demo"

# --- Servicio Gunicorn ---
cat > /etc/systemd/system/sgr.service <<UNIT
[Unit]
Description=SGR (Gunicorn)
After=network.target postgresql.service

[Service]
User=sgr
WorkingDirectory=$APP
EnvironmentFile=$APP/.env
ExecStart=$APP/.venv/bin/gunicorn config.wsgi:application --bind 127.0.0.1:8000 --workers 2
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now sgr

# --- Nginx con HTTPS (certificado autofirmado creado por sgr-ip.sh) ---
cat > /etc/nginx/sites-available/sgr <<NGINX
server {
    listen 80;
    return 301 https://\$host\$request_uri;
}
server {
    listen 443 ssl;
    ssl_certificate /etc/ssl/certs/sgr.crt;
    ssl_certificate_key /etc/ssl/private/sgr.key;
    client_max_body_size 6M;
    location /static/ { alias $APP/staticfiles/; }
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Real-IP \$remote_addr;
    }
}
NGINX
ln -sf /etc/nginx/sites-available/sgr /etc/nginx/sites-enabled/sgr
rm -f /etc/nginx/sites-enabled/default
systemctl restart nginx
echo "SGR instalado; la IP se actualiza en cada arranque (sgr-ip.service)."
