FROM node:24.19.0-bookworm-slim@sha256:3638d9a6fe4030bd716be989438248074489337ba3275657f93595428be4fc03 AS build

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm install --global npm@11.6.0 && npm ci
COPY . .
RUN npm run build


FROM nginxinc/nginx-unprivileged:1.31.4-trixie AS runtime

ENV NGINX_ENVSUBST_FILTER=^API_UPSTREAM$
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist/ /usr/share/nginx/html/

USER nginx
EXPOSE 8080
