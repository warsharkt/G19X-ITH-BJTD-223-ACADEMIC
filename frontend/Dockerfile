# Tablero de Talentia Insights: se compila con Node y lo sirve nginx, que
# tambien reenvia /api a la API. Asi el navegador ve una sola direccion.
# Fijada por digest: la etiqueta puede cambiar de contenido sin avisar. Dependabot
# (.github/dependabot.yml) propone las actualizaciones.
FROM node:24-alpine@sha256:8a32c8cf649a49915a66e81e7a609223c708d0adabf288ee3f4077d765542f85 AS compilar
WORKDIR /web
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# La API se llama en la misma direccion del tablero (nginx.conf)
ENV VITE_API_URL=/api
RUN npm run build

FROM nginx:1.31-alpine@sha256:785835ea65db4bba6f021acc0f3be91b0fef76a53fe41f8588c6698d2aed0606
# openssl: genera un certificado autofirmado si la empresa no pone el suyo
# apk upgrade: la imagen puede traer paquetes con arreglos ya publicados
RUN apk upgrade --no-cache && apk add --no-cache openssl && rm -f /etc/nginx/conf.d/default.conf
COPY nginx/comun.conf nginx/http.conf nginx/https.conf nginx/limites.conf nginx/proxy-api.conf /etc/nginx/talentia/
# Al arrancar elige HTTP o HTTPS segun WEB_HTTPS y WEB_ESCUCHA
COPY nginx/talentia-https.sh /docker-entrypoint.d/40-talentia-https.sh
# sin CR por si el repositorio se clono en Windows con finales de linea CRLF
RUN sed -i 's/\r$//' /docker-entrypoint.d/40-talentia-https.sh && chmod +x /docker-entrypoint.d/40-talentia-https.sh
COPY --from=compilar /web/dist /usr/share/nginx/html
EXPOSE 80 443
