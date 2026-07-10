import { http } from './request'

export interface HelloData {
  message: string
}

export function getHello() {
  return http.get<HelloData>('/hello')
}
