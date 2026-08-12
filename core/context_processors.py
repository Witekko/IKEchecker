from .models import Announcement, UserAnnouncementRead

def active_announcement(request):
    if request.user.is_authenticated:
        read_ids = UserAnnouncementRead.objects.filter(user=request.user).values_list('announcement_id', flat=True)
        latest = Announcement.objects.filter(is_active=True).exclude(id__in=read_ids).order_by('-created_at').first()
        return {'active_announcement': latest}
    return {'active_announcement': None}
