async function request(method, path, body) {
  const res = await fetch(`/api${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let msg = `请求失败（${res.status}）`;
    try {
      const data = await res.json();
      if (data.detail) msg = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    } catch { /* ignore */ }
    throw new Error(msg);
  }
  if (res.status === 204) return null;
  return res.json();
}

const qs = (params) => {
  const q = new URLSearchParams();
  Object.entries(params || {}).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") q.set(k, v);
  });
  const s = q.toString();
  return s ? `?${s}` : "";
};

export const api = {
  customers: () => request("GET", "/customers"),
  createCustomer: (b) => request("POST", "/customers", b),
  items: () => request("GET", "/service-items"),
  createItem: (b) => request("POST", "/service-items", b),
  rules: (p) => request("GET", `/rules${qs(p)}`),
  saveRule: (b) => request("POST", "/rules", b),
  deleteRule: (id) => request("DELETE", `/rules/${id}`),
  usage: (p) => request("GET", `/usage${qs(p)}`),
  addUsage: (b) => request("POST", "/usage", b),
  importUsage: (records) => request("POST", "/usage/import", { records }),
  bills: (p) => request("GET", `/bills${qs(p)}`),
  bill: (id) => request("GET", `/bills/${id}`),
  preview: (p) => request("GET", `/bills/preview${qs(p)}`),
  generate: (b) => request("POST", "/bills/generate", b),
  demoReset: () => request("POST", "/demo/reset"),
};
