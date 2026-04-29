<?php
require_once __DIR__ . '/include/api_client.php';

header('Content-Type: application/json');

register_shutdown_function(function() {
    $e = error_get_last();
    if ($e && in_array($e['type'], [E_ERROR, E_PARSE, E_CORE_ERROR, E_COMPILE_ERROR])) {
        if (!headers_sent()) header('Content-Type: application/json');
        echo json_encode(['error' => $e['message']]);
    }
});

$action = $_GET['action'] ?? '';
switch ($action) {
    case 'config_get':
        echo json_encode(daemon_get('/api/config'));
        break;
    case 'config_save':
        $data = json_decode($_POST['payload'] ?? '{}', true) ?? [];
        echo json_encode(daemon_post('/api/config', $data));
        break;
    case 'scan_start':
        echo json_encode(daemon_post('/api/scan/start'));
        break;
    case 'scan_cancel':
        echo json_encode(daemon_post('/api/scan/cancel'));
        break;
    case 'scan_status':
        echo json_encode(daemon_get('/api/scan/status'));
        break;
    case 'scan_approve':
        $data = json_decode($_POST['payload'] ?? '{}', true) ?? [];
        echo json_encode(daemon_post('/api/scan/approve', $data));
        break;
    case 'move_file':
        $data = json_decode($_POST['payload'] ?? '{}', true) ?? [];
        echo json_encode(daemon_post('/api/scan/move-file', $data, 600));
        break;
    case 'scan_undo':
        echo json_encode(daemon_post('/api/scan/undo'));
        break;
    case 'manual_review':
        echo json_encode(daemon_get('/api/manual-review'));
        break;
    case 'review_identify':
        $id = $_GET['id'] ?? '';
        $data = json_decode($_POST['payload'] ?? '{}', true) ?? [];
        echo json_encode(daemon_post("/api/manual-review/{$id}/identify", $data));
        break;
    case 'transcribe':
        $id = $_GET['id'] ?? '';
        echo json_encode(daemon_post("/api/manual-review/{$id}/transcribe", [], 300));
        break;
    case 'move_unidentified':
        $id = $_GET['id'] ?? '';
        echo json_encode(daemon_post("/api/manual-review/{$id}/move-unidentified"));
        break;
    case 'browse':
        $path = $_GET['path'] ?? '/mnt';
        echo json_encode(daemon_get('/api/browse?path=' . urlencode($path)));
        break;
    case 'logs':
        echo json_encode(daemon_get('/api/logs'));
        break;
    default:
        http_response_code(404);
        echo json_encode(['error' => 'Unknown action']);
}
