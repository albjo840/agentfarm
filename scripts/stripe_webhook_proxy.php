<?php
/**
 * Stripe Webhook Proxy
 *
 * Upload this file to: https://lenajosefsson.se/webhook/stripe/index.php
 * (create folders 'webhook/stripe' and put this as index.php)
 *
 * This forwards Stripe webhook requests to your AgentFarm server.
 */

// Your AgentFarm server URL (internal network or public)
$TARGET_URL = 'http://taborsen.duckdns.org:8080/webhook/stripe';

// Only accept POST requests
if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    echo json_encode(['error' => 'Method not allowed']);
    exit;
}

// Get the raw POST body (Stripe sends JSON)
$payload = file_get_contents('php://input');

// Get the Stripe signature header
$signature = isset($_SERVER['HTTP_STRIPE_SIGNATURE']) ? $_SERVER['HTTP_STRIPE_SIGNATURE'] : '';

// Forward the request to AgentFarm server
$ch = curl_init($TARGET_URL);
curl_setopt_array($ch, [
    CURLOPT_POST => true,
    CURLOPT_POSTFIELDS => $payload,
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_HTTPHEADER => [
        'Content-Type: application/json',
        'Stripe-Signature: ' . $signature,
    ],
    CURLOPT_TIMEOUT => 30,
    CURLOPT_CONNECTTIMEOUT => 10,
]);

$response = curl_exec($ch);
$http_code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
$error = curl_error($ch);
curl_close($ch);

// Log for debugging (check your server's error log)
error_log("Stripe webhook proxy: HTTP $http_code, Error: $error, Response: " . substr($response, 0, 200));

// Return the response from AgentFarm
http_response_code($http_code ?: 502);
header('Content-Type: application/json');
echo $response ?: json_encode(['error' => 'Proxy error: ' . $error]);
