from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from accounts.views import (
    signup_view, EmailPasswordLoginView, post_login_router,
    onboarding_view, profile_view
)
from django.contrib.auth.views import LogoutView
from django.http import HttpResponse
import os
from accounts.views import my_style_view,add_typed_post_view,save_onboarding_inline, upload_file_view, delete_upload_view, regenerate_style_profile_view, credits_view, mock_add_credits, generate_view, history_view, content_detail_view, approve_content_view, improve_content_view, change_topic_view, calendar_view, auto_populate_view

urlpatterns = [
    path("admin/", admin.site.urls),
    path("signup/", signup_view, name="signup"),
    path("login/", EmailPasswordLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("", post_login_router, name="post_login_router"),
    path("onboarding/", onboarding_view, name="onboarding"),
    path("profile/", profile_view, name="profile"),
    path("my-style/", my_style_view, name="my_style"),
    path("my-style/upload/", upload_file_view, name="upload_file"),
    path("my-style/delete/<int:upload_id>/", delete_upload_view, name="delete_upload"),
    path("my-style/regenerate/", regenerate_style_profile_view, name="regenerate_style"),
    path("credits/", credits_view, name="credits"),
    path("credits/add/", mock_add_credits, name="mock_add_credits"),
    path("generate/", generate_view, name="generate"),
    path("history/", history_view, name="history"),
    path("content/<int:content_id>/", content_detail_view, name="content_detail"),
    path("content/<int:content_id>/approve/", approve_content_view, name="approve_content"),
    path("content/<int:content_id>/improve/", improve_content_view, name="improve_content"),
    path("content/<int:content_id>/change-topic/", change_topic_view, name="change_topic"),
    path("calendar/", calendar_view, name="calendar"),
    path("calendar/auto-populate/", auto_populate_view, name="auto_populate"),
    path("my-style/add-typed/", add_typed_post_view, name="add_typed_post"),
    path("my-style/save-prefs/", save_onboarding_inline, name="save_onboarding_inline"),
    path("healthz/", lambda r: HttpResponse("ok", content_type="text/plain")),
]

# Serve media in dev OR when explicitly allowed
if settings.DEBUG or os.getenv("SERVE_MEDIA", "true").lower() in ("1", "true", "yes"):
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
