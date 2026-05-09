FROM nginx:1.27-alpine

# 将生成好的报告复制进 nginx 根目录
COPY output/report_latest.html /usr/share/nginx/html/index.html

# 404 也指向报告（SPA-style fallback）
RUN echo 'server { \
    listen 8080; \
    root /usr/share/nginx/html; \
    location / { \
        try_files $uri $uri/ /index.html; \
    } \
    gzip on; \
    gzip_types text/html text/css application/javascript; \
}' > /etc/nginx/conf.d/default.conf

EXPOSE 8080
