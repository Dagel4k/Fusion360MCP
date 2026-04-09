import adsk.core
import traceback

def run(context):
    try:
        from . import commands
        commands.start()
    except Exception as e:
        app = adsk.core.Application.get()
        if app and app.userInterface:
            app.userInterface.messageBox('Failed:\n{}'.format(traceback.format_exc()))
        log_path = os.path.join(os.path.dirname(__file__), 'error_log.txt')
        with open(log_path, "w") as f:
            f.write(traceback.format_exc())

def stop(context):
    try:
        from . import commands
        commands.stop()
    except Exception as e:
        app = adsk.core.Application.get()
        if app and app.userInterface:
            app.userInterface.messageBox('Failed:\n{}'.format(traceback.format_exc()))
        log_path = os.path.join(os.path.dirname(__file__), 'error_log.txt')
        with open(log_path, "w") as f:
            f.write(traceback.format_exc())