from .models import Announcement

def active_announcement(request):
    if request.user.is_authenticated:
        latest = Announcement.objects.filter(is_active=True).order_by('-created_at').first()
        return {'active_announcement': latest}
    return {'active_announcement': None}
