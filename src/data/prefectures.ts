import type { Prefecture } from '../types'

export const JAPAN_PREFECTURES: Prefecture[] = [
  { id: 'tokyo', name: 'Tokyo', lat: 35.6762, lng: 139.6503 },
  { id: 'osaka', name: 'Osaka', lat: 34.6937, lng: 135.5023 },
  { id: 'kanagawa', name: 'Kanagawa', lat: 35.4478, lng: 139.6425 },
  { id: 'aichi', name: 'Aichi', lat: 35.1802, lng: 136.9066 },
  { id: 'hyogo', name: 'Hyogo', lat: 34.6901, lng: 135.1955 },
  { id: 'hokkaido', name: 'Hokkaido', lat: 43.0642, lng: 141.3469 },
  { id: 'fukuoka', name: 'Fukuoka', lat: 33.5904, lng: 130.4017 },
  { id: 'kyoto', name: 'Kyoto', lat: 35.0116, lng: 135.7681 },
  { id: 'miyagi', name: 'Miyagi', lat: 38.2688, lng: 140.8721 },
  { id: 'shizuoka', name: 'Shizuoka', lat: 34.9756, lng: 138.3827 },
  { id: 'hiroshima', name: 'Hiroshima', lat: 34.3853, lng: 132.4553 },
  { id: 'chiba', name: 'Chiba', lat: 35.6074, lng: 140.1065 },
  { id: 'okinawa', name: 'Okinawa', lat: 26.2124, lng: 127.6792 },
  { id: 'nagano', name: 'Nagano', lat: 36.6513, lng: 138.181 },
  { id: 'kumamoto', name: 'Kumamoto', lat: 32.7898, lng: 130.7417 },
]

export const JAPAN_MAP_CENTER: [number, number] = [36.2, 137.5]
export const JAPAN_MAP_ZOOM = 6.2

export const JAPAN_VIEW_BOUNDS: [[number, number], [number, number]] = [
  [24.0, 122.5],
  [46.2, 146.5],
]
