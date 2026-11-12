from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("users", views.UserAdminViewSet, basename="users")

urlpatterns = [
    path("auth/login/", views.LoginView.as_view()),
    path("auth/logout/", views.LogoutView.as_view()),
    path("auth/signup/", views.SignupView.as_view()),
    path("auth/me/", views.MeView.as_view()),
    path("auth/change-password/", views.ChangePasswordView.as_view()),
    path("auth/forgot-password/", views.ForgotPasswordView.as_view()),
    path("auth/verify-otp/", views.VerifyOTPView.as_view()),
    path("auth/reset-password/", views.ResetPasswordView.as_view()),
    path("auth/organizations/", views.OrganizationsView.as_view()),
    path("", include(router.urls)),
]
