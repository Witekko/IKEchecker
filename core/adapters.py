from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth import get_user_model
from allauth.account.models import EmailAddress

User = get_user_model()

class MySocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        """
        Automatically links a social account (like Google) to an existing local user
        if the email addresses match, bypassing verification restrictions for trusted providers.
        """
        # If the social account is already connected to a user, do nothing
        if sociallogin.is_existing:
            return

        # Get email from Google profile
        email = sociallogin.account.extra_data.get('email')
        if not email:
            return

        try:
            # 1. Attempt to find user in the standard User table
            user = User.objects.get(email__iexact=email)
            
            # 2. Ensure an EmailAddress record exists and is marked as verified for this user
            email_addr, created = EmailAddress.objects.get_or_create(
                user=user,
                email=email,
                defaults={'verified': True, 'primary': True}
            )
            if not email_addr.verified:
                email_addr.verified = True
                email_addr.save()

            # 3. Connect the social account to the user
            sociallogin.connect(request, user)
        except User.DoesNotExist:
            pass
