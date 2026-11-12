"""URL routes for the matching app."""

from django.urls import path

from matching import views

urlpatterns = [
    path("search", views.MatchSearchView.as_view(), name="matching-search"),
    path("score", views.MatchScoreView.as_view(), name="matching-score"),
    path("categories", views.RoleCategoryListView.as_view(), name="matching-categories"),
]
