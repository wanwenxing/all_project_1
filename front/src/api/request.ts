import axios, { type AxiosError, type AxiosRequestConfig } from 'axios'
import { message } from 'antd'
import type { ApiResponse } from './types'

const AUTH_PATHS = ['/login', '/register']
const AUTH_API_PATTERN = /\/auth\/(login|register)$/

function getErrorMessage(error: AxiosError<ApiResponse>): string {
  const data = error.response?.data
  return data?.message || error.message || '网络错误，请稍后重试'
}

function shouldRedirectToLogin(error: AxiosError): boolean {
  const requestUrl = error.config?.url || ''
  const isAuthRequest = AUTH_API_PATTERN.test(requestUrl)
  const isAuthPage = AUTH_PATHS.includes(window.location.pathname)
  return !isAuthRequest && !isAuthPage
}

const request = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
})

request.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    // 让浏览器自动带 multipart boundary
    if (config.data instanceof FormData) {
      delete config.headers['Content-Type']
    }
    return config
  },
  (error) => Promise.reject(error),
)

request.interceptors.response.use(
  (response) => {
    const accessToken = response.headers['x-access-token']
    if (accessToken) {
      localStorage.setItem('token', accessToken)
    }

    const res = response.data as ApiResponse

    if (res && typeof res === 'object' && 'code' in res) {
      if (res.code === 0 || res.code === 200) {
        return res.data
      }
      message.error(res.message || '请求失败')
      return Promise.reject(new Error(res.message || '请求失败'))
    }

    return response.data
  },
  (error: AxiosError<ApiResponse>) => {
    const status = error.response?.status
    const msg = getErrorMessage(error)

    message.error(msg)

    if (status === 401) {
      localStorage.removeItem('token')

      if (shouldRedirectToLogin(error)) {
        window.location.replace('/login')
      }
    }

    return Promise.reject(error)
  },
)

export const http = {
  get<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    return request.get(url, config)
  },

  post<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    return request.post(url, data, config)
  },

  put<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    return request.put(url, data, config)
  },

  patch<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    return request.patch(url, data, config)
  },

  delete<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    return request.delete(url, config)
  },
}

export default request
