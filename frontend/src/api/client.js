import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api',
  withCredentials: true,
})

export function errorMessage(err) {
  const d = err?.response?.data?.detail
  if (typeof d === 'string') return d
  if (Array.isArray(d) && d.length) return d.map((x) => x.msg).join('. ')
  if (!err?.response) return 'Cannot reach the server. Is the backend running?'
  return 'Something went wrong. Please try again.'
}

export default api
