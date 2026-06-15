import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Mock fetch before importing the module
const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

// We need to import after mocking fetch
import { api } from '../api/client';

// ─── Helpers ───────────────────────────────────────────

function mockFetchResponse(data: any, status = 200) {
  mockFetch.mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? 'OK' : 'Unauthorized',
    json: () => Promise.resolve(data),
  });
}

function mockFetchNetworkError(message = 'Network failure') {
  mockFetch.mockRejectedValue(new Error(message));
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

afterEach(() => {
  localStorage.clear();
});

// ─── Tests ─────────────────────────────────────────────

describe('client.ts - Request Interceptor', () => {
  it('makes GET request with correct URL', async () => {
    mockFetchResponse({ code: 0, data: { id: 1 } });

    const result = await api.get('/api/test');

    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [url, options] = mockFetch.mock.calls[0];
    expect(url).toContain('/api/test');
    expect(options.method).toBeUndefined(); // GET is default
  });

  it('makes POST request with JSON body', async () => {
    mockFetchResponse({ code: 0, data: { id: 2 } });

    const body = { name: 'test' };
    const result = await api.post('/api/test', body);

    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [url, options] = mockFetch.mock.calls[0];
    expect(options.method).toBe('POST');
    expect(options.headers['Content-Type']).toBe('application/json');
    expect(JSON.parse(options.body)).toEqual(body);
  });

  it('makes PUT request with JSON body', async () => {
    mockFetchResponse({ code: 0 });

    const body = { status: 'updated' };
    await api.put('/api/test/1', body);

    const [url, options] = mockFetch.mock.calls[0];
    expect(options.method).toBe('PUT');
    expect(JSON.parse(options.body)).toEqual(body);
  });

  it('returns parsed response on success', async () => {
    const responseData = { code: 0, data: { balance: 100 } };
    mockFetchResponse(responseData);

    const result = await api.get('/api/balance');
    expect(result).toEqual(responseData);
  });

  it('returns error response for non-ok HTTP status', async () => {
    mockFetchResponse({ code: 401, message: 'Unauthorized' }, 401);

    const result = await api.get('/api/protected');
    expect(result.code).toBe(401);
    expect(result.message).toBe('HTTP 401: Unauthorized');
  });

  it('returns network error message on fetch failure', async () => {
    mockFetchNetworkError('Failed to fetch');

    const result = await api.get('/api/test');
    expect(result.code).toBe(500);
    expect(result.message).toBe('Failed to fetch');
  });
});

describe('client.ts - Token Injection', () => {
  it('injects token into Authorization header when token exists', async () => {
    localStorage.setItem('token', 'my-bearer-token');
    mockFetchResponse({ code: 0, data: 'ok' });

    await api.get('/api/secure');

    const [url, options] = mockFetch.mock.calls[0];
    expect(options.headers['Authorization']).toBe('Bearer my-bearer-token');
  });

  it('does not include Authorization header when no token', async () => {
    mockFetchResponse({ code: 0, data: 'ok' });

    await api.get('/api/public');

    const [url, options] = mockFetch.mock.calls[0];
    expect(options.headers['Authorization']).toBeUndefined();
  });

  it('includes Content-Type header on all requests', async () => {
    mockFetchResponse({ code: 0 });

    await api.get('/api/test');

    const [url, options] = mockFetch.mock.calls[0];
    expect(options.headers['Content-Type']).toBe('application/json');
  });
});

describe('client.ts - 401 Handling', () => {
  it('returns HTTP 401 status code when server returns 401', async () => {
    localStorage.setItem('token', 'expired-token');
    mockFetchResponse({ code: 401, message: 'token expired' }, 401);

    const result = await api.get('/api/admin');

    expect(result.code).toBe(401);
    expect(result.message).toContain('401');
  });

  it('returns 401 from response body code field', async () => {
    mockFetchResponse({ code: 401, message: '未授权，请重新登录' }, 200);

    const result = await api.get('/api/protected');
    expect(result.code).toBe(401);
    expect(result.message).toBe('未授权，请重新登录');
  });

  it('still sends token on API calls even after potential expiration', async () => {
    localStorage.setItem('token', 'still-sent-token');
    mockFetchResponse({ code: 401 }, 401);

    await api.get('/api/protected');

    const [url, options] = mockFetch.mock.calls[0];
    expect(options.headers['Authorization']).toBe('Bearer still-sent-token');
  });
});

describe('client.ts - Token helpers', () => {
  it('api.saveToken stores token in localStorage', () => {
    api.saveToken('new-token');
    expect(localStorage.getItem('token')).toBe('new-token');
  });

  it('api.loadToken retrieves token from localStorage', () => {
    localStorage.setItem('token', 'existing-token');
    expect(api.loadToken()).toBe('existing-token');
  });

  it('api.loadToken returns null when no token stored', () => {
    expect(api.loadToken()).toBeNull();
  });

  it('api.removeToken clears token from localStorage', () => {
    localStorage.setItem('token', 'remove-me');
    api.removeToken();
    expect(localStorage.getItem('token')).toBeNull();
  });
});
