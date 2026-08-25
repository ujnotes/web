<?php
declare(strict_types=1);

require_once __DIR__ . '/sync_firebase_rewrites.php';

function assert_true(bool $condition, string $message): void
{
    if (!$condition) {
        fwrite(STDERR, "FAIL: {$message}\n");
        exit(1);
    }
}

$root = sys_get_temp_dir() . '/sync_firebase_rewrites_' . bin2hex(random_bytes(8));
$public = $root . '/public';
$artifactDir = $public . '/computer/program/ie';
if (!mkdir($artifactDir, 0777, true) && !is_dir($artifactDir)) {
    fwrite(STDERR, "FAIL: could not create {$artifactDir}\n");
    exit(1);
}
file_put_contents($artifactDir . '/index.json', '{}');
$firebase = $root . '/firebase.json';
file_put_contents($firebase, json_encode([
    'hosting' => [
        'rewrites' => [
            [
                'regex' => '^/(.+)\\.json$',
                'destination' => '/:1/index.json',
            ],
            [
                'source' => '/hi',
                'destination' => '/hi/root/index.html',
            ],
        ],
    ],
], JSON_UNESCAPED_SLASHES));

assert_true(synchronize($firebase, $public) === 1, 'expected one generated rewrite');

$rewrites = json_decode(file_get_contents($firebase), true, 512, JSON_THROW_ON_ERROR)['hosting']['rewrites'];
assert_true(
    in_array([
        'source' => '/computer/program/ie.json',
        'destination' => '/computer/program/ie/index.json',
    ], $rewrites, true),
    'missing canonical json rewrite'
);
assert_true(
    in_array([
        'source' => '/hi',
        'destination' => '/hi/root/index.html',
    ], $rewrites, true),
    'missing preserved /hi rewrite'
);
foreach ($rewrites as $item) {
    assert_true(!isset($item['regex']), 'generic regex rewrite was not removed');
}

$cleanup = static function (string $path) use (&$cleanup): void {
    if (is_file($path)) {
        unlink($path);
        return;
    }
    if (!is_dir($path)) {
        return;
    }
    foreach (scandir($path) ?: [] as $name) {
        if ($name === '.' || $name === '..') {
            continue;
        }
        $cleanup($path . '/' . $name);
    }
    rmdir($path);
};
$cleanup($root);

echo "OK\n";
