# Frontend image - just the static HTML/CSS/JS (Dashboard.html, Notification.html,
# History.html, Login.html, config.js, common.js, send-notification.js, ...)
# served by nginx. No build step, same files as `python3 -m http.server`,
# just containerized.
FROM nginx:alpine

# Custom server block: this app has no index.html (pages are Login.html,
# Dashboard.html, ...), so nginx's own default page would otherwise show
# instead of the app at "/".
COPY nginx.conf /etc/nginx/conf.d/default.conf

COPY . /usr/share/nginx/html

# Make sure everything is world-readable regardless of the permissions the
# source files happened to have on the host (nginx's worker processes run
# as a non-root user, so a file that's only owner-readable on the host -
# e.g. from being edited by a different tool/account - would 403 otherwise).
RUN chmod -R a+rX /usr/share/nginx/html

EXPOSE 80
