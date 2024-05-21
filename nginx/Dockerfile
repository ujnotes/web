# syntax=docker/dockerfile:1.4

FROM nginx:latest

RUN <<EOF
apt-get update
apt-get install wget
apt-get install minify
EOF

EXPOSE 80 443

WORKDIR /app
