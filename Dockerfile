FROM nginx:1.27-alpine

# 主报告
COPY output/report_latest.html /usr/share/nginx/html/index.html

# 原有顶级项目库（AR-001 ~ AR-113）
RUN mkdir -p /usr/share/nginx/html/projects
COPY output/projects.html /usr/share/nginx/html/projects/index.html

# 全量项目库（AR-00001 ~ AR-42653+）
RUN mkdir -p /usr/share/nginx/html/all
COPY output/full_projects.html         /usr/share/nginx/html/all/index.html
COPY output/full_projects_data.json    /usr/share/nginx/html/all/full_projects_data.json

RUN printf 'server {\n\
    listen 8080;\n\
    root /usr/share/nginx/html;\n\
    gzip on;\n\
    gzip_types text/html text/css application/javascript application/json;\n\
    gzip_min_length 1024;\n\
\n\
    location / {\n\
        try_files $uri $uri/ /index.html;\n\
    }\n\
\n\
    location /projects/ {\n\
        try_files $uri $uri/ /projects/index.html;\n\
    }\n\
\n\
    location /all/ {\n\
        try_files $uri $uri/ /all/index.html;\n\
    }\n\
}\n' > /etc/nginx/conf.d/default.conf

EXPOSE 8080
