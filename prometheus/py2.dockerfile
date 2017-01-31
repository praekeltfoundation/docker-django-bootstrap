FROM praekeltfoundation/django-bootstrap:py2

# Build nginx-lua-http dynamic modules
ENV NGINX_GPG_KEY=B0F4253373F8F6F510D42178520A9993A1C052F8 \
    NGX_DEVEL_KIT_VERSION=0.3.0 \
    NGX_LUA_VERSION=0.10.7
RUN set -x \
    && buildDeps=' \
        gcc \
        libc6-dev \
        libluajit-5.1-dev \
        libpcre3-dev \
        libssl-dev \
        make \
        wget \
        zlib1g-dev \
    ' \
    && apt-get-install.sh $buildDeps libluajit-5.1-2 \
    \
    && wget -O nginx.tar.gz "http://nginx.org/download/nginx-${NGINX_VERSION%-*}.tar.gz" \
    && wget -O nginx.tar.gz.asc "http://nginx.org/download/nginx-${NGINX_VERSION%-*}.tar.gz.asc" \
    && export GNUPGHOME="$(mktemp -d)" \
    && gpg --keyserver ha.pool.sks-keyservers.net --recv-keys "$NGINX_GPG_KEY" \
    && gpg --batch --verify nginx.tar.gz.asc nginx.tar.gz \
    && rm -r "$GNUPGHOME" nginx.tar.gz.asc \
    && mkdir -p /usr/src/nginx \
    && tar -xzC /usr/src/nginx --strip-components=1 -f nginx.tar.gz \
    && rm nginx.tar.gz \
    \
    && wget -O ngx_devel_kit.tar.gz "https://github.com/simpl/ngx_devel_kit/archive/v$NGX_DEVEL_KIT_VERSION.tar.gz" \
    && mkdir -p /usr/src/ngx_devel_kit \
    && tar -xzC /usr/src/ngx_devel_kit --strip-components=1 -f ngx_devel_kit.tar.gz \
    && rm ngx_devel_kit.tar.gz \
    \
    && wget -O ngx_lua.tar.gz "https://github.com/openresty/lua-nginx-module/archive/v$NGX_LUA_VERSION.tar.gz" \
    && mkdir -p /usr/src/ngx_lua \
    && tar -xzC /usr/src/ngx_lua --strip-components=1 -f ngx_lua.tar.gz \
    && rm ngx_lua.tar.gz \
    \
    && cd /usr/src/nginx \
    && export LUAJIT_LIB=/usr/lib/x86_64-linux-gnu \
    && export LUAJIT_INC=/usr/include/luajit-2.0 \
# HACK: Use the same configure options used to build our Nginx to build modules so that they're compatible
    && nginx -V 2>&1 | grep 'configure arguments' | cut -d':' -f2 \
        | xargs ./configure  \
            --add-dynamic-module=/usr/src/ngx_devel_kit \
            --add-dynamic-module=/usr/src/ngx_lua \
    && make modules \
    && cp objs/ndk_http_module.so /usr/lib/nginx/modules \
    && cp objs/ngx_http_lua_module.so /usr/lib/nginx/modules \
    \
    && rm -rf /usr/src/nginx /usr/src/ngx_devel_kit /usr/src/ngx_lua \
    && apt-get-purge.sh $buildDeps

# Install nginx-lua-prometheus
# FIXME: No release yet... install from known-good commit
ENV NGINX_LUA_PROMETHEUS_GIT_SHA 0f229261cc45bb1e23c5cb418ad130d183229a7f
RUN set -x \
    && apt-get-install.sh wget \
    && wget -O nginx-lua-prometheus.tar.gz "https://github.com/knyar/nginx-lua-prometheus/archive/$NGINX_LUA_PROMETHEUS_GIT_SHA.tar.gz" \
    && mkdir /nginx-lua-prometheus \
    && tar -xzC /nginx-lua-prometheus --strip-components=1 -f nginx-lua-prometheus.tar.gz \
    && rm nginx-lua-prometheus.tar.gz \
    && apt-get-purge.sh wget

COPY nginx/ /etc/nginx/
