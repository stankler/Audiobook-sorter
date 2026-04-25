<?php
require_once __DIR__ . '/include/api_client.php';

header('Content-Type: application/json');

$action = $_GET['action'] ?? '';
switch ($action) {
    case 'config_get':
        echo json_encode(daemon_get('/api/config'));
        break;
    case 'config_save':
        $data = json_decode(file_get_contents('php://input'), true) ?? [];
        echo json_encode(daemon_post('/api/config', $data));
        break;
    case 'scan_start':
        echo json_encode(daemon_post('/api/scan/start'));
        break;
    case 'scan_status':
        echo json_encode(daemon_get('/api/scan/status'));
        break;
    case 'scan_approve':
        $data = json_decode(file_get_contents('php://input'), true) ?? [];
        echo json_encode(daemon_post('/api/scan/approve', $data));
        break;
    case 'scan_undo':
        echo json_encode(daemon_post('/api/scan/undo'));
        break;
    case 'manual_review':
        echo json_encode(daemon_get('/api/manual-review'));
        break;
    case 'move_unidentified':
        $id = $_GET['id'] ?? '';
        echo json_encode(daemon_post("/api/manual-review/{$id}/move-unidentified"));
        break;
    case 'logs':
        echo json_encode(daemon_get('/api/logs'));
        break;
    default:
        http_response_code(404);
        echo json_encode(['error' => 'Unknown action']);
}
