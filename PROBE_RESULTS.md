# PROBE_RESULTS

Generated: 2026-09-01T01:37:05-04:00

Every URL below was fetched live. Status code, content type and the first 500 characters of the body are recorded verbatim.

## GSD site type

**Question:** Is it WordPress, and is there an events post type?

### `https://www.gsd.harvard.edu/wp-json/wp/v2/`

- Final URL: `https://www.gsd.harvard.edu/wp-json/wp/v2/`
- Status: `200`
- Content-Type: `application/json; charset=UTF-8`
- Bytes: `598633`
- Signals:
  - WordPress markers present
  - JSON response

```
{"namespace":"wp\/v2","routes":{"\/wp\/v2":{"namespace":"wp\/v2","methods":["GET"],"endpoints":[{"methods":["GET"],"args":{"namespace":{"default":"wp\/v2","required":false},"context":{"default":"view","required":false}}}],"_links":{"self":[{"href":"https:\/\/www.gsd.harvard.edu\/wp-json\/wp\/v2"}]}},"\/wp\/v2\/gsd-search-modal":{"namespace":"wp\/v2","methods":["GET"],"endpoints":[{"methods":["GET"],"args":{"search":{"description":"Search term.","type":"string","required":false},"page":{"descript
```

### `https://www.gsd.harvard.edu/wp-json/wp/v2/types`

- Final URL: `https://www.gsd.harvard.edu/wp-json/wp/v2/types`
- Status: `200`
- Content-Type: `application/json; charset=UTF-8`
- Bytes: `36627`
- Signals:
  - WordPress markers present
  - JSON response

```
{"page":{"description":"","hierarchical":true,"has_archive":false,"name":"Pages","slug":"page","icon":"dashicons-admin-page","taxonomies":["office","page_type","affiliation","department","academic_program","editor_office"],"rest_base":"pages","rest_namespace":"wp\/v2","template":[["core\/pattern",{"slug":"gsd\/template-single-page"}]],"template_lock":false,"yoast_head":null,"yoast_head_json":null,"_links":{"collection":[{"href":"https:\/\/www.gsd.harvard.edu\/wp-json\/wp\/v2\/types"}],"wp:items"
```

### `https://www.gsd.harvard.edu/events/`

- Final URL: `https://www.gsd.harvard.edu/public-programs/`
- Status: `200`
- Content-Type: `text/html; charset=UTF-8`
- Bytes: `301758`
- Signals:
  - iCal link found on page: http://criticallandscapes.com/
  - 1 JSON-LD block(s); first 200 chars: {"@context":"https:\/\/schema.org","@graph":[{"@type":"WebPage","@id":"https:\/\/www.gsd.harvard.edu\/public-programs\/","url":"https:\/\/www.gsd.harvard.edu\/public-programs\/","name":"Public Program

```
<!DOCTYPE html>
<html lang="en-US" class="no-js" data-theme="light">
	<head>
		<script>
			(() => {
				const match = document.cookie.match(/(?:^|; )theme=(dark|light)/);
				const cookieTheme = match ? match[1] : null;
				const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
				const theme = cookieTheme || (systemPrefersDark ? 'dark' : 'light');
				document.documentElement.dataset.theme = theme;
			})();
		</script>
		<meta charset="UTF-8" />
<script>
var gform
```

## Media Lab feed

**Question:** Is there an RSS feed?

### `https://www.media.mit.edu/events/feed/`

- Final URL: `https://www.media.mit.edu/events/feed/`
- Status: `404`
- Content-Type: `text/html`
- Bytes: `125161`

```
<!DOCTYPE html>
<html>
    <head>
        <meta charset='utf-8' />
        <meta http-equiv='X-UA-Compatible' content='IE=edge' />
        <meta name='viewport' content='width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no' />
        <meta name='msapplication-tap-highlight' content='no' />

        <title>404 Not Found &mdash; MIT Media Lab</title>

        <style>
            @font-face {
                font-family: 'Neue Haas Grotesk Display';
                font-style: no
```

### `https://www.media.mit.edu/events/feed.xml`

- Final URL: `https://www.media.mit.edu/events/feed.xml`
- Status: `404`
- Content-Type: `text/html`
- Bytes: `125161`

```
<!DOCTYPE html>
<html>
    <head>
        <meta charset='utf-8' />
        <meta http-equiv='X-UA-Compatible' content='IE=edge' />
        <meta name='viewport' content='width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no' />
        <meta name='msapplication-tap-highlight' content='no' />

        <title>404 Not Found &mdash; MIT Media Lab</title>

        <style>
            @font-face {
                font-family: 'Neue Haas Grotesk Display';
                font-style: no
```

### `https://www.media.mit.edu/events/`

- Final URL: `https://www.media.mit.edu/events/`
- Status: `200`
- Content-Type: `text/html; charset=utf-8`
- Bytes: `65119`

```


<!DOCTYPE html>
<html>
    <head>
        <meta charset='utf-8' />
        <meta http-equiv='X-UA-Compatible' content='IE=edge' />
        <meta name='viewport' content='width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no' />
        <meta name='msapplication-tap-highlight' content='no' />
        
            
                


<meta name='description' content='The MIT Media Lab is an interdisciplinary research lab that encourages             the unconventional mixing and 
```

## Art Museums structure

**Question:** Embedded JSON on the page? What does Add to Calendar point at?

### `https://harvardartmuseums.org/calendar`

- Final URL: `https://harvardartmuseums.org/calendar`
- Status: `200`
- Content-Type: `text/html; charset=utf-8`
- Bytes: `1100440`
- Signals:
  - 1 JSON-LD block(s); first 200 chars: {
  "@context" : "http://schema.org",
  "@type" : "Organization",
  "name" : "Harvard Art Museums",
  "url" : "http://www.harvardartmuseums.org",
  "sameAs" : [
    "http://www.facebook.com/harvardart

```
<!doctype html>
<html lang="en" class="w-screen">
<head>
  <meta charset="utf-8" />
<meta http-equiv="X-UA-Compatible" content="IE=Edge">

<title> Calendar | Harvard Art Museums </title>
<meta name="description" content="The calendar provides information about events at the Harvard Art Museums." />
<meta name="author" content="Harvard " />

<meta name="ids-success" content="L05L4RK5">
<meta name="ids-error" content="ELURJ3JQ">

<meta name="csrf-token" content="991IQZNHZTD6uXnSYdcNBJIb4RIYbDrudtQ
```

### `https://harvardartmuseums.org/calendar/exhibitions`

- Final URL: `https://harvardartmuseums.org/calendar/exhibitions`
- Status: `404`
- Content-Type: `text/html; charset=utf-8`
- Bytes: `3185`

```
<!doctype html>
<html lang="en">
<head>
	<meta charset="utf-8">
	<meta http-equiv="X-UA-Compatible" content="IE=edge,chrome=1">
	<title>Error | Harvard Art Museums</title>
	<meta name="description" content="Page currently unavailable." />
    <meta property="og:title" content="Error | Harvard Art Museums" />
    <meta property="og:description" content="Page currently unavailable." />
	<meta name="viewport" content="width=device-width">

	<style type="text/css">
	@font-face {
	  font-family: "Neu
```

## CSAIL ICS address

**Question:** Real URL behind Subscribe to Calendar.

### `https://www.csail.mit.edu/events`

- Final URL: `https://www.csail.mit.edu/events`
- Status: `200`
- Content-Type: `text/html; charset=UTF-8`
- Bytes: `79451`
- Signals:
  - iCal link found on page: https://www.google.com/calendar/render?cid=webcal://csail-live-2025.csail.mit.edu/event_calendar.ics?v1

```
<!DOCTYPE html>
<html lang="en" dir="ltr">
<head>
  <meta charset="utf-8" />
<script async src="https://www.googletagmanager.com/gtag/js?id=UA-5382944-3"></script>
<script>window.dataLayer = window.dataLayer || [];function gtag(){dataLayer.push(arguments)};gtag("js", new Date());gtag("set", "developer_id.dMDhkMT", true);gtag("config", "UA-5382944-3", {"groups":"default","anonymize_ip":true,"page_placeholder":"PLACEHOLDER_page_path","allow_ad_personalization_signals":false});</script>
<meta name=
```

### `https://calendar.csail.mit.edu/`

- Final URL: `https://tig.csail.mit.edu/events-reservations/calendar/`
- Status: `200`
- Content-Type: `text/html`
- Bytes: `31618`

```
<!DOCTYPE html>
<html>
  <head>
    <title>The Infrastructure Group at MIT CSAIL</title>
    
      <meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<meta name="revised" content="2026-08-24T13:15:07 EDT">
<title>Calendar :: The Infrastructure Group at MIT CSAIL</title>
<link rel="shortcut icon" href="/images/favicon.png" type="image/x-icon" />
<link href="/css/font-awesome.min.css" rel="stylesheet">
<link href="/css/nu
```

## Loeb Library ICS address

**Question:** Same as above.

### `https://libcal.gsd.harvard.edu/calendars`

- Final URL: `https://libcal.gsd.harvard.edu/calendars`
- Status: `200`
- Content-Type: `text/html; charset=utf-8`
- Bytes: `69916`
- Signals:
  - LibCal / Springshare markers present

```
        <!DOCTYPE html>
<html lang="en">
<head>
    <!-- iid: 3651 -->
    <meta charset="utf-8">
    <meta http-equiv="X-UA-Compatible" content="IE=Edge">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
            
    <link href="https://static-assets-us.libcal.com/bootstrap_16/bootstrap3_16.min.css" rel="stylesheet">


    <link href="//cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css" rel="stylesheet">
    <link href="https://static-asset
```

### `https://libcal.gsd.harvard.edu/calendar`

- Final URL: `https://libcal.gsd.harvard.edu/calendar`
- Status: `200`
- Content-Type: `text/html; charset=utf-8`
- Bytes: `69916`
- Signals:
  - LibCal / Springshare markers present

```
        <!DOCTYPE html>
<html lang="en">
<head>
    <!-- iid: 3651 -->
    <meta charset="utf-8">
    <meta http-equiv="X-UA-Compatible" content="IE=Edge">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
            
    <link href="https://static-assets-us.libcal.com/bootstrap_16/bootstrap3_16.min.css" rel="stylesheet">


    <link href="//cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css" rel="stylesheet">
    <link href="https://static-asset
```

## Localist API docs

**Question:** Confirm paging / date-range / filter parameter names.

### `https://developer.localist.com/doc/api`

- Final URL: `https://developer.localist.com/doc/api`
- Status: `200`
- Content-Type: `text/html; charset=utf-8`
- Bytes: `1137593`
- Signals:
  - Localist markers present

```
<!DOCTYPE html>
<html>

<head>
  <meta charset="utf8" />
  <title>Localist API</title>
  <!-- needed for adaptive design -->
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body {
      padding: 0;
      margin: 0;
    }
  </style>
  <script src="https://cdn.redocly.com/redoc/v2.5.3/bundles/redoc.standalone.js" integrity="sha384-xiEssMQFSpSfLbzRZCGfxxIM5QDb2DTrU6vyoZdp2sV1L6pmOMy6MpTtUoLbpC96" crossorigin="anonymous"></script><style data-styled="true" data-st
```
