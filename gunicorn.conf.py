bind = "0.0.0.0:5000"

worker_class = "gevent"
workers = 1

accesslog = "-"

wsgi_app = "heket_web:app"

def post_worker_init(worker):
    from heket_web import start_background_services
    start_background_services()