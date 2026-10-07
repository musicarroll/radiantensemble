from django.contrib.auth import get_user_model
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import MemberProfile, Post


@receiver(post_save, sender=get_user_model())
def create_member_profile(sender, instance, created, **kwargs):
    if created:
        MemberProfile.objects.get_or_create(
            user=instance,
            defaults={"display_name": instance.get_full_name() or instance.username},
        )


@receiver(post_delete, sender=Post)
def delete_post_graphic(sender, instance, **kwargs):
    if instance.graphic:
        instance.graphic.delete(save=False)
