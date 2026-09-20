FROM php:8.3-fpm-alpine
RUN apk add --no-cache git unzip libpq-dev oniguruma-dev && docker-php-ext-install pdo_pgsql mbstring
COPY --from=composer:2 /usr/bin/composer /usr/bin/composer
WORKDIR /var/www/html
COPY composer.json composer.lock ./
RUN composer install --no-interaction --prefer-dist
COPY . .
RUN mkdir -p var/cache var/log && chown -R www-data:www-data var
USER www-data
