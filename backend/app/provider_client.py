from typing import Any
import os
import httpx

from app.storage import storage_registry


class ProviderError(Exception):
    """Base exception for provider communication errors."""
    pass


class ProviderTimeoutError(ProviderError):
    """Raised when the provider request times out."""
    pass


class ProviderConnectionError(ProviderError):
    """Raised when connecting to the provider fails."""
    pass


class ProviderResponseError(ProviderError):
    """Raised when the provider returns an HTTP error status or invalid payload."""
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


class WeatherProviderClient:
    """
    Controlled HTTP client for requesting weather provider endpoints.
    Enforces connection/read timeouts, error handling, and configurable URLs.
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = 5.0,
        connect_timeout: float = 2.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self.connect_timeout = connect_timeout
        self._client = client

    def get_provider_url(self) -> str:
        """Resolve the provider URL from explicit setting, env var, or storage registry."""
        if self.base_url:
            return self.base_url

        env_url = os.environ.get("WEATHER_PROVIDER_URL")
        if env_url:
            return env_url

        service = storage_registry.get_service("weather")
        if service and service.get("base_url"):
            return service["base_url"]

        return "http://127.0.0.1:8000/api/v1/mock/weather"

    def fetch_weather(
        self,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Request weather data from the upstream provider.
        Handles network errors, timeouts, and JSON decoding safely.
        """
        url = self.get_provider_url()

        timeout_config = httpx.Timeout(self.timeout, connect=self.connect_timeout)

        try:
            if self._client:
                response = self._client.get(url, params=params, timeout=timeout_config)
            else:
                with httpx.Client(timeout=timeout_config) as client:
                    response = client.get(url, params=params)

            if response.status_code >= 400:
                raise ProviderResponseError(
                    f"Weather provider returned HTTP {response.status_code}: {response.text}",
                    status_code=502,
                )

            try:
                data = response.json()
            except Exception as exc:
                raise ProviderResponseError(
                    f"Weather provider returned invalid JSON: {str(exc)}",
                    status_code=502,
                ) from exc

            if not isinstance(data, dict):
                raise ProviderResponseError(
                    "Weather provider response must be a JSON object.",
                    status_code=502,
                )

            return data

        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("Weather provider request timed out.") from exc
        except (httpx.ConnectError, httpx.NetworkError) as exc:
            raise ProviderConnectionError(
                f"Could not connect to weather provider at {url}: {str(exc)}"
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderConnectionError(
                f"Weather provider request failed: {str(exc)}"
            ) from exc


# Default client instance
weather_provider_client = WeatherProviderClient()
