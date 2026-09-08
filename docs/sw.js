/**
 * @file sw.js
 * @brief 서비스 워커 - 기본 캐싱 전략
 */

const CACHE_NAME = 'csat-benchmark-v1'
const BASE_PATH = '/CSAT-benchmark'

// 캐시할 정적 에셋
const STATIC_ASSETS = [
  `${BASE_PATH}/`,
  `${BASE_PATH}/index.html`,
  `${BASE_PATH}/benchmarks.json`,
  `${BASE_PATH}/model_metadata.json`,
  `${BASE_PATH}/all_results.json`,
  `${BASE_PATH}/token_usage.json`
]

/**
 * @brief 설치 이벤트 - 정적 에셋 캐시
 */
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => {
        return cache.addAll(STATIC_ASSETS)
      })
      .then(() => {
        // 대기 중인 서비스 워커 즉시 활성화
        return self.skipWaiting()
      })
  )
})

/**
 * @brief 활성화 이벤트 - 오래된 캐시 정리
 */
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((cacheNames) => {
        return Promise.all(
          cacheNames
            .filter((name) => name !== CACHE_NAME)
            .map((name) => caches.delete(name))
        )
      })
      .then(() => {
        // 모든 클라이언트 제어
        return self.clients.claim()
      })
  )
})

/**
 * @brief 페치 이벤트 - 네트워크 우선, 캐시 폴백
 */
self.addEventListener('fetch', (event) => {
  // 같은 오리진 요청만 처리
  if (!event.request.url.startsWith(self.location.origin)) {
    return
  }

  event.respondWith(
    fetch(event.request)
      .then((response) => {
        // 성공적인 응답은 캐시에 저장
        if (response.status === 200) {
          const responseClone = response.clone()
          caches.open(CACHE_NAME)
            .then((cache) => {
              cache.put(event.request, responseClone)
            })
        }
        return response
      })
      .catch(() => {
        // 네트워크 실패 시 캐시에서 반환
        return caches.match(event.request)
      })
  )
})
