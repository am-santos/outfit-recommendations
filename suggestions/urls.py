from django.urls import path

from suggestions import views

app_name = "suggestions"

urlpatterns = [
    path("", views.TodayView.as_view(), name="today"),
]
