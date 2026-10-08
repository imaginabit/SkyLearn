from django.urls import path
from . import views

urlpatterns = [
    path("<slug>/quizzes/", views.quiz_list, name="quiz_index"),
    path("progress/", view=views.QuizUserProgressView.as_view(), name="quiz_progress"),
    # path('marking/<int:pk>/', view=QuizMarkingList.as_view(), name='quiz_marking'),
    path("marking_list/", view=views.QuizMarkingList.as_view(), name="quiz_marking"),
    path(
        "marking/<int:pk>/",
        view=views.QuizMarkingDetail.as_view(),
        name="quiz_marking_detail",
    ),
    path("<int:pk>/<slug>/take/", view=views.QuizTake.as_view(), name="quiz_take"),
    path("<slug>/quiz_add/", views.QuizCreateView.as_view(), name="quiz_create"),
    path("<slug>/<int:pk>/add/", views.QuizUpdateView.as_view(), name="quiz_update"),
    path("<slug>/<int:pk>/delete/", views.quiz_delete, name="quiz_delete"),
    path(
        "mc-question/add/<slug>/<int:quiz_id>/",
        views.MCQuestionCreate.as_view(),
        name="mc_create",
    ),
    # Partidas en vivo (al estilo Kahoot)
    path("live/create/", views.live_create_pick, name="live_create_pick"),
    path("live/create/<slug>/", views.live_create, name="live_create"),
    path("live/join/", views.live_join, name="live_join"),
    path("live/host/<str:code>/", views.live_host, name="live_host"),
    path("live/play/<str:code>/", views.live_play, name="live_play"),
    path("live/<str:code>/state/", views.live_state, name="live_state"),
    path("live/<str:code>/action/", views.live_action, name="live_action"),
    path("live/<str:code>/answer/", views.live_answer, name="live_answer"),
    # path('mc-question/add/<int:pk>/<quiz_pk>/', MCQuestionCreate.as_view(), name='mc_create'),
]
