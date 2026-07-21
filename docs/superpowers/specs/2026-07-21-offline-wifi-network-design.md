# Offline Wi-Fi Network Display Design

## Purpose

Make the AIPI-Lite LCD identify the configured Wi-Fi network whenever it shows
the `OFFLINE` status. This lets an operator confirm which local network the
device is attempting to join without exposing its password, local service URL,
or other credentials.

## Scope

The existing offline transition will provide the configured `WIFI_SSID` as
display detail. The offline display will render a short `Wi-Fi: <SSID>` note
while retaining its reconnect instruction. If no local Wi-Fi configuration is
available, it will instead render `Wi-Fi not configured`.

The display must use its existing text-width handling so a long SSID cannot
overflow the 128 by 128 LCD. The configured SSID is display-only; it must not
change Wi-Fi connection behavior, endpoint validation, button handling, or
logging of secrets.

## Components and Data Flow

1. The push-to-talk controller already loads the local Wi-Fi configuration.
2. When connection startup or a reconnect fails, the controller enters the
   offline state with the configured SSID, or the explicit no-configuration
   fallback, as its display detail.
3. `StatusOutputs` sends that detail to `StatusDisplay.render_status`.
4. The display composes the offline screen with the network note and existing
   reconnect guidance, using the current safe truncation and line-layout path.

## Error Handling and Privacy

- A missing configuration or absent SSID is a normal offline state, not an
  exception; the display explicitly says that Wi-Fi is not configured.
- Only the SSID is displayed. Wi-Fi passwords, approved hostnames, and local
  service URLs remain undisclosed.
- Long SSIDs are truncated by the display renderer rather than overflowing or
  disrupting the reconnect instructions.

## Validation

- Add host-side tests covering a configured SSID and the no-configuration
  fallback during offline transitions.
- Verify that existing offline button-retry behavior remains unchanged.
- Update user and firmware-tree documentation to describe the added note.
- Run the repository-required unit, shell-syntax, and whitespace checks before
  the implementation commit.
