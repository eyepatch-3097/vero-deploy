from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from .models import User, Onboarding
from .models import Upload, StyleProfile, CreditTransaction, ContentItem, ContentVersion
from .models import GuidelinePillar, GuidelineSchedule
from .utils import record_credit_change  # for the admin action


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("username","email","credits","onboarding_completed","is_staff","last_login")
    list_filter = ("onboarding_completed","is_staff","is_active")
    search_fields = ("username","email")

    # Show our custom fields on the user change page
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Creator App Fields", {
            "fields": ("credits", "timezone", "onboarding_completed"),
        }),
    )

    actions = ["add_10_credits"]

    @admin.action(description="Add 10 credits")
    def add_10_credits(self, request, queryset):
        for user in queryset:
            record_credit_change(user, 10, "TOPUP", f"Admin action +10 by {request.user.username}")
        self.message_user(request, f"Added 10 credits to {queryset.count()} user(s).")

    # If admin edits the credits field directly on the user form, log the delta
    def save_model(self, request, obj, form, change):
        if change and "credits" in form.changed_data:
            # old value before save
            old = User.objects.get(pk=obj.pk).credits
            super().save_model(request, obj, form, change)
            delta = obj.credits - old
            if delta != 0:
                # Create a transaction WITHOUT changing credits again
                CreditTransaction.objects.create(
                    user=obj,
                    kind="TOPUP" if delta > 0 else "IMPROVE",  # use IMRPOVE as generic negative adjust; change label if you prefer
                    amount=delta,
                    balance_after=obj.credits,
                    note=f"Manual admin edit by {request.user.username}",
                )
            return
        super().save_model(request, obj, form, change)

@admin.register(Onboarding)
class OnboardingAdmin(admin.ModelAdmin):
    list_display = ("user","industry","created_at")
    search_fields = ("user__username","user__email","industry")

@admin.register(Upload)
class UploadAdmin(admin.ModelAdmin):
    list_display = ("user","file_type","bytes","created_at")
    search_fields = ("user__username","user__email")

@admin.register(StyleProfile)
class StyleProfileAdmin(admin.ModelAdmin):
    list_display = ("user","version","active","created_at")
    list_filter = ("active",)

@admin.register(CreditTransaction)
class CreditTransactionAdmin(admin.ModelAdmin):
    list_display = ("user","kind","amount","balance_after","created_at")
    list_filter = ("kind",)
    search_fields = ("user__username","user__email")

@admin.register(ContentItem)
class ContentItemAdmin(admin.ModelAdmin):
    list_display = ("user","type","topic","status","created_at")
    list_filter = ("type","status")
    search_fields = ("topic","user__username","user__email")

@admin.register(ContentVersion)
class ContentVersionAdmin(admin.ModelAdmin):
    list_display = ("content","version_no","created_at")
    search_fields = ("content__topic",)

@admin.register(GuidelinePillar)
class GuidelinePillarAdmin(admin.ModelAdmin):
    list_display = ("user","title","keywords")
    search_fields = ("title","user__username","user__email")

@admin.register(GuidelineSchedule)
class GuidelineScheduleAdmin(admin.ModelAdmin):
    list_display = ("user","day_of_week","pillar","notes")
    list_filter = ("day_of_week",)