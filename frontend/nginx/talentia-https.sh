#!/bin/sh
# Elige la configuracion de nginx al arrancar el contenedor (lo corre el
# entrypoint de la imagen de nginx, antes de iniciarlo).
#
#   WEB_HTTPS=auto (por defecto): HTTPS si el tablero se abre a la red
#                  (WEB_ESCUCHA distinto de 127.0.0.1); si no, HTTP.
#   WEB_HTTPS=si:  siempre HTTPS.
#   WEB_HTTPS=no:  solo HTTP, y se niega a arrancar si el tablero se abre a
#                  la red: las contrasenas y los codigos viajarian sin cifrar.
#
# Con HTTPS usa certs/talentia.crt y certs/talentia.key (el certificado de la
# empresa). Si no existen, genera uno autofirmado para WEB_NOMBRE.
set -eu

ESCUCHA="${WEB_ESCUCHA:-127.0.0.1}"
MODO="${WEB_HTTPS:-auto}"
PUERTO="${WEB_PUERTO_HTTPS:-8443}"
NOMBRE="${WEB_NOMBRE:-localhost}"
CERTS=/etc/nginx/certs
DESTINO=/etc/nginx/conf.d/default.conf

local_solo=no
case "$ESCUCHA" in
    127.0.0.1|localhost) local_solo=si ;;
esac

case "$MODO" in
    si) https=si ;;
    no)
        if [ "$local_solo" = no ]; then
            echo "Talentia: WEB_ESCUCHA=$ESCUCHA abre el tablero a la red y WEB_HTTPS=no lo dejaria sin cifrar." >&2
            echo "Talentia: usa WEB_HTTPS=si (o auto), o publica solo en 127.0.0.1." >&2
            exit 1
        fi
        https=no ;;
    auto) if [ "$local_solo" = si ]; then https=no; else https=si; fi ;;
    *)
        echo "Talentia: WEB_HTTPS debe ser auto, si o no (vale '$MODO')." >&2
        exit 1 ;;
esac

if [ "$https" = no ]; then
    cp /etc/nginx/talentia/http.conf "$DESTINO"
    echo "Talentia: tablero por HTTP, solo en este equipo ($ESCUCHA)."
    exit 0
fi

if [ ! -s "$CERTS/talentia.crt" ] || [ ! -s "$CERTS/talentia.key" ]; then
    case "$NOMBRE" in
        localhost|127.0.0.1) san="DNS:localhost,IP:127.0.0.1" ;;
        *[!0-9.]*) san="DNS:$NOMBRE,DNS:localhost,IP:127.0.0.1" ;;
        *) san="IP:$NOMBRE,DNS:localhost,IP:127.0.0.1" ;;
    esac
    mkdir -p "$CERTS"
    openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes -days 825 \
        -subj "/CN=$NOMBRE" -addext "subjectAltName=$san" \
        -keyout "$CERTS/talentia.key" -out "$CERTS/talentia.crt" 2>/dev/null
    chmod 600 "$CERTS/talentia.key"
    echo "Talentia: se genero un certificado autofirmado para $NOMBRE en certs/ (pon ahi el de la empresa para quitar el aviso del navegador)."
fi

sed "s/PUERTO_HTTPS/$PUERTO/" /etc/nginx/talentia/https.conf > "$DESTINO"
echo "Talentia: tablero por HTTPS en el puerto $PUERTO; el HTTP redirige ahi."
