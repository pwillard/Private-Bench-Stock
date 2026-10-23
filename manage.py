"""Entry points.

    python manage.py serve [--host 0.0.0.0] [--port 8080]   production server (waitress)
    python manage.py <flask command>                         e.g. import-mysql, backup
"""
import sys

from benchstock import create_app


def serve(argv):
    import argparse

    from waitress import serve as waitress_serve

    ap = argparse.ArgumentParser(prog="manage.py serve")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--threads", type=int, default=4)
    a = ap.parse_args(argv)
    app = create_app()
    print(f"BenchStock serving on http://{a.host}:{a.port}/  (database: {app.config['DATABASE']})")
    waitress_serve(app, host=a.host, port=a.port, threads=a.threads,
                   max_request_body_size=app.config["MAX_CONTENT_LENGTH"])


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        serve(sys.argv[2:])
    else:
        from flask.cli import FlaskGroup
        FlaskGroup(create_app=create_app).main(args=sys.argv[1:], prog_name="manage.py")
