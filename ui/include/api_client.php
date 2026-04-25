<?php
define('DAEMON_URL', 'http://127.0.0.1:7171');

function daemon_get(string $path): array {
    $ch = curl_init(DAEMON_URL . $path);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT => 10,
    ]);
    $body = curl_exec($ch);
    $code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    if ($body === false || $code >= 400) return ['error' => "HTTP $code"];
    return json_decode($body, true) ?? ['error' => 'Invalid JSON'];
}

function daemon_post(string $path, array $data = []): array {
    $ch = curl_init(DAEMON_URL . $path);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_POST => true,
        CURLOPT_POSTFIELDS => json_encode($data),
        CURLOPT_HTTPHEADER => ['Content-Type: application/json'],
        CURLOPT_TIMEOUT => 10,
    ]);
    $body = curl_exec($ch);
    $code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    if ($body === false || $code >= 400) return ['error' => "HTTP $code"];
    return json_decode($body, true) ?? ['error' => 'Invalid JSON'];
}
