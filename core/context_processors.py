from .models import Announcement, UserAnnouncementRead

def active_announcement(request):
    if request.user.is_authenticated:
        read_ids = UserAnnouncementRead.objects.filter(user=request.user).values_list('announcement_id', flat=True)
        active_list = list(Announcement.objects.filter(is_active=True).exclude(id__in=read_ids).order_by('-created_at'))
        return {'active_announcements': active_list}
    return {'active_announcements': []}
