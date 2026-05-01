from .models import History

def syncHistory(user, device_id):
    histories = History.objects.filter(user=None, device_id=device_id)
    histories.update(user=user)