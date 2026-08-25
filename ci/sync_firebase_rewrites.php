<?php
declare(strict_types=1);

const EXTENSIONS = ['json', 'jpg', 'svg'];
const DROPPED_REGEXES = [
    '^/(.+)\\.json$',
    '^/(.+)\\.jpg$',
    '^/(.+)\\.svg$',
];

function usage(): void
{
    fwrite(STDERR, "usage: sync_firebase_rewrites.php FIREBASE_JSON PUBLIC_DIR\n");
    exit(1);
}

function posix_relative(string $from, string $to): string
{
    $from = rtrim(str_replace('\\', '/', $from), '/');
    $to = str_replace('\\', '/', $to);
    if (!str_starts_with($to, $from . '/') && $to !== $from) {
        throw new RuntimeException("Path {$to} is not under {$from}");
    }
    return $to === $from ? '.' : substr($to, strlen($from) + 1);
}

function collect_index_paths(string $publicRoot, string $extension): array
{
    $paths = [];
    $iterator = new RecursiveIteratorIterator(
        new RecursiveDirectoryIterator($publicRoot, FilesystemIterator::SKIP_DOTS)
    );
    foreach ($iterator as $file) {
        if (!$file->isFile()) {
            continue;
        }
        if (strcasecmp($file->getFilename(), "index.{$extension}") !== 0) {
            continue;
        }
        $paths[] = str_replace('\\', '/', $file->getPathname());
    }
    sort($paths, SORT_STRING);
    return $paths;
}

function canonical_rewrites(string $publicRoot): array
{
    $publicRoot = rtrim(str_replace('\\', '/', $publicRoot), '/');
    $rewrites = [];
    foreach (EXTENSIONS as $extension) {
        foreach (collect_index_paths($publicRoot, $extension) as $artifact) {
            $slug = posix_relative($publicRoot, dirname($artifact));
            if ($slug === '.') {
                continue;
            }
            $canonical = $publicRoot . '/' . $slug . '.' . $extension;
            if (is_file($canonical)) {
                continue;
            }
            $rewrites[] = [
                'source' => "/{$slug}.{$extension}",
                'destination' => "/{$slug}/index.{$extension}",
            ];
        }
    }
    return $rewrites;
}

function encode_firebase_json(array $config): string
{
    $json = json_encode(
        $config,
        JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR
    );
    $json = preg_replace_callback('/^( +)/m', static function (array $match): string {
        return str_repeat(' ', (int) (strlen($match[1]) / 2));
    }, $json);
    return $json . "\n";
}

function synchronize(string $firebasePath, string $publicRoot): int
{
    $config = json_decode(file_get_contents($firebasePath), true, 512, JSON_THROW_ON_ERROR);
    if (!isset($config['hosting']) || !is_array($config['hosting'])) {
        $config['hosting'] = [];
    }
    $existing = $config['hosting']['rewrites'] ?? [];
    if (!is_array($existing)) {
        $existing = [];
    }

    $generated = canonical_rewrites($publicRoot);
    $generatedSources = [];
    foreach ($generated as $item) {
        $generatedSources[$item['source']] = true;
    }

    $preserved = [];
    foreach ($existing as $item) {
        if (!is_array($item)) {
            continue;
        }
        $source = $item['source'] ?? null;
        $regex = $item['regex'] ?? null;
        if (is_string($source) && isset($generatedSources[$source])) {
            continue;
        }
        if (is_string($regex) && in_array($regex, DROPPED_REGEXES, true)) {
            continue;
        }
        $preserved[] = $item;
    }

    $config['hosting']['rewrites'] = array_merge($generated, $preserved);
    file_put_contents($firebasePath, encode_firebase_json($config));
    return count($generated);
}

if (PHP_SAPI === 'cli' && realpath($_SERVER['SCRIPT_FILENAME'] ?? '') === realpath(__FILE__)) {
    if (($argc ?? 0) !== 3) {
        usage();
    }
    $count = synchronize($argv[1], $argv[2]);
    echo "Synchronized {$count} canonical Firebase rewrites.\n";
}
