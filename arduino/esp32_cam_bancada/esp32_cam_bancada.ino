// Bancada: Arduino IDE, placa AI Thinker ESP32-CAM, core esp32 da Espressif.
#include <WiFi.h>
#include "esp_camera.h"
#include "esp_http_server.h"
#include "esp_timer.h"
#define CAMERA_MODEL_AI_THINKER
#include "camera_pins.h"

const char *SSID = "Carrinho-CAM";
const char *PASSWORD = "Carrinho123"; // Altere: 8 a 63 caracteres.

static esp_err_t capture(httpd_req_t *req) {
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("Erro: captura falhou");
    return httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "Captura falhou");
  }
  if (fb->format != PIXFORMAT_JPEG) {
    esp_camera_fb_return(fb);
    return httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "Formato invalido");
  }
  // Ambos os timestamps usam o relogio monotônico da ESP, reiniciado no boot.
  int64_t captured = (int64_t)fb->timestamp.tv_sec * 1000000LL + fb->timestamp.tv_usec;
  int64_t age = esp_timer_get_time() - captured;
  char ageText[32];
  snprintf(ageText, sizeof(ageText), "%lld", (long long)age);
  httpd_resp_set_type(req, "image/jpeg");
  httpd_resp_set_hdr(req, "Cache-Control", "no-store, no-cache, must-revalidate");
  httpd_resp_set_hdr(req, "X-Frame-Age-Us", ageText);
  esp_err_t result = httpd_resp_send(req, (const char *)fb->buf, fb->len);
  esp_camera_fb_return(fb); // Inclusive em desconexao/erro de envio.
  if (result != ESP_OK) Serial.printf("Erro de envio: 0x%x\n", result);
  return result;
}

static void fatal(const char *message) {
  Serial.println(message);
  while (true) delay(1000);
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  if (strlen(PASSWORD) < 8 || strlen(PASSWORD) > 63) fatal("Erro: senha deve ter 8 a 63 caracteres");
  if (!psramFound()) fatal("Erro: PSRAM nao encontrada; confira perfil AI Thinker/PSRAM");
  camera_config_t c = {};
  c.ledc_channel = LEDC_CHANNEL_0;
  c.ledc_timer = LEDC_TIMER_0;
  c.pin_d0 = Y2_GPIO_NUM; c.pin_d1 = Y3_GPIO_NUM;
  c.pin_d2 = Y4_GPIO_NUM; c.pin_d3 = Y5_GPIO_NUM;
  c.pin_d4 = Y6_GPIO_NUM; c.pin_d5 = Y7_GPIO_NUM;
  c.pin_d6 = Y8_GPIO_NUM; c.pin_d7 = Y9_GPIO_NUM;
  c.pin_xclk = XCLK_GPIO_NUM; c.pin_pclk = PCLK_GPIO_NUM;
  c.pin_vsync = VSYNC_GPIO_NUM; c.pin_href = HREF_GPIO_NUM;
  c.pin_sccb_sda = SIOD_GPIO_NUM; c.pin_sccb_scl = SIOC_GPIO_NUM;
  c.pin_pwdn = PWDN_GPIO_NUM; c.pin_reset = RESET_GPIO_NUM;
  c.xclk_freq_hz = 20000000;
  c.pixel_format = PIXFORMAT_JPEG;
  c.frame_size = FRAMESIZE_QVGA; // 320 x 240
  c.jpeg_quality = 12;
  c.fb_count = 2;
  c.fb_location = CAMERA_FB_IN_PSRAM;
  c.grab_mode = CAMERA_GRAB_LATEST;
  esp_err_t err = esp_camera_init(&c);
  if (err != ESP_OK) {
    Serial.printf("Erro de inicializacao da camera: 0x%x\n", err);
    fatal("Confira sensor, flex e alimentacao; depois reinicie");
  }
  WiFi.mode(WIFI_AP);
  IPAddress ip(192,168,4,1), mask(255,255,255,0);
  if (!WiFi.softAPConfig(ip, ip, mask) || !WiFi.softAP(SSID, PASSWORD))
    fatal("Erro de inicializacao do ponto de acesso");
  httpd_config_t config = HTTPD_DEFAULT_CONFIG();
  config.server_port = 80;
  config.send_wait_timeout = 3;
  config.recv_wait_timeout = 3;
  httpd_handle_t server = nullptr;
  if (httpd_start(&server, &config) != ESP_OK) fatal("Erro ao iniciar HTTP");
  httpd_uri_t route = {};
  route.uri = "/capture";
  route.method = HTTP_GET;
  route.handler = capture;
  if (httpd_register_uri_handler(server, &route) != ESP_OK) fatal("Erro ao registrar /capture");
  Serial.printf("Rede: %s\nhttp://192.168.4.1/capture\n", SSID);
}
void loop() { delay(1000); }
