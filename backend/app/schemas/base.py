from pydantic import BaseModel, ConfigDict


class ResponseModel(BaseModel):
    """Base for response schemas that have fields with defaults.

    The API always serializes those fields, but OpenAPI would otherwise list
    them as optional, and every generated client type would then carry a `?`
    the server never honours.
    """

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)
