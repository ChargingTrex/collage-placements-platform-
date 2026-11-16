"""Declared filters: an undeclared query parameter is a 400 (core.filters)."""

from django_filters import rest_framework as filters

from core.filters import HumanKeyFilter, HumanKeyInFilter
from opportunities.models import Application, Opportunity


class OpportunityFilter(filters.FilterSet):
    status = filters.ChoiceFilter(choices=Opportunity.Status.choices)
    role_type = filters.ChoiceFilter(choices=Opportunity.RoleType.choices)
    company_id = filters.UUIDFilter(field_name="company_id")

    class Meta:
        model = Opportunity
        fields = ["status", "role_type", "company_id"]


class ApplicationFilter(filters.FilterSet):
    opportunity = filters.UUIDFilter(field_name="opportunity_id")
    status = filters.ChoiceFilter(choices=Application.Status.choices)
    prn = HumanKeyFilter(field_name="prn")
    prns = HumanKeyInFilter(field_name="prn")

    class Meta:
        model = Application
        fields = ["opportunity", "status", "prn", "prns"]
