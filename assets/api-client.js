(function exposeHousingApi() {
  const configuredBase = document
    .querySelector('meta[name="api-base-url"]')
    ?.getAttribute("content")
    ?.replace(/\/$/, "");
  const baseUrl = configuredBase || "http://localhost:8000/api/v1";

  async function request(path, timeoutMs = 2500) {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(`${baseUrl}${path}`, {
        headers: { Accept: "application/json" },
        signal: controller.signal,
      });
      if (!response.ok) throw new Error(`API ${response.status}`);
      return await response.json();
    } finally {
      window.clearTimeout(timeout);
    }
  }

  window.HousingApi = {
    regionSummary(status) {
      const query = status ? `?status=${encodeURIComponent(status)}` : "";
      return request(`/regions/summary${query}`);
    },
    announcements(params = {}) {
      return request(`/announcements?${new URLSearchParams(params)}`);
    },
  };
})();
