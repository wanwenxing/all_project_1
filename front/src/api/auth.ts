import { http } from './request'

export interface LoginParams {
  username: string
  password: string
}

export interface RegisterParams {
  username: string
  email: string
  password: string
}

export interface TokenData {
  access_token: string
  token_type: string
}

export interface UserPublic {
  id: number
  username: string
  email: string
  is_active: boolean
  created_at: string
}

export interface AuthData {
  token: TokenData
  user: UserPublic
}

export function login(data: LoginParams) {
  return http.post<AuthData>('/auth/login', data)
}

export function register(data: RegisterParams) {
  return http.post<AuthData>('/auth/register', data)
}
