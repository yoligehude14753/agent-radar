FROM nginx:1.27-alpine

# 主报告
COPY output/report_latest.html /usr/share/nginx/html/index.html

# 项目库（/projects/ 路径）
RUN mkdir -p /usr/share/nginx/html/projects
COPY output/projects.html /usr/share/nginx/html/projects/index.html

RUN printf 'server {\n\
    listen 8080;\n\
    root /usr/share/nginx/html;\n\
    gzip on;\n\
    gzip_types text/html text/css application/javascript;\n\
\n\
    # 主报告\n\
    location / {\n\
        try_files $uri $uri/ /index.html;\n\
    }\n\
\n\
    # 项目库\n\
    location /projects/ {\n\
        try_files $uri $uri/ /projects/index.html;\n\
    }\n\
}\n' > /etc/nginx/conf.d/default.conf

EXPOSE 8080
