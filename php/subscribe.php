<?php
// Adds an email to this site's Brevo list. Config is written at deploy time.
header('Content-Type: application/json');
header('Cache-Control: no-store');

function reply($ok, $message, $code = 200) {
    http_response_code($code);
    echo json_encode(['ok' => $ok, 'message' => $message]);
    exit;
}

if ($_SERVER['REQUEST_METHOD'] !== 'POST') reply(false, 'Method not allowed.', 405);
if (!empty($_POST['website'])) reply(true, 'Thanks for subscribing!'); // honeypot

$email = trim($_POST['email'] ?? '');
if (!filter_var($email, FILTER_VALIDATE_EMAIL)) reply(false, 'Please enter a valid email address.', 400);

$config = @include __DIR__ . '/subscribe-config.php';
if (!is_array($config) || empty($config['api_key']) || empty($config['list_id'])) {
    reply(false, 'Subscriptions are not open yet. Please check back soon.', 503);
}

$ch = curl_init('https://api.brevo.com/v3/contacts');
curl_setopt_array($ch, [
    CURLOPT_POST => true,
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_TIMEOUT => 15,
    CURLOPT_HTTPHEADER => [
        'api-key: ' . $config['api_key'],
        'Content-Type: application/json',
        'Accept: application/json',
    ],
    CURLOPT_POSTFIELDS => json_encode([
        'email' => $email,
        'listIds' => [(int)$config['list_id']],
        'updateEnabled' => true,
    ]),
]);
$body = curl_exec($ch);
$status = curl_getinfo($ch, CURLINFO_HTTP_CODE);
curl_close($ch);

if ($status >= 200 && $status < 300) reply(true, "You're subscribed! Look for the roundup on Monday.");
error_log("Brevo subscribe failed ($status): $body");
reply(false, 'Something went wrong. Please try again later.', 502);
