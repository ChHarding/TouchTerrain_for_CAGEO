# Needed to avoid timing out for long-ish jobs (> 30 secs?)
# Note that if you've got another router in front of this, like haproxy or heroku or openshift, 
# you might need to change the timeout there too
timeout = 5 * 60

# required for newer python container
accesslog = '-'
bind = ['0.0.0.0:8080']

wsgi_app = "touchterrain.server.TouchTerrain_app:app"
