import AppKit
import CoreLocation
import Foundation

final class KumaLocationDelegate: NSObject, CLLocationManagerDelegate {
    private let manager = CLLocationManager()
    private var geocoder: CLGeocoder?
    private var finished = false

    override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyHundredMeters
    }

    private func authorizationName(_ status: CLAuthorizationStatus) -> String {
        switch status {
        case .notDetermined: return "not_determined"
        case .restricted: return "restricted"
        case .denied: return "denied"
        case .authorizedAlways: return "authorized_always"
        case .authorizedWhenInUse: return "authorized_when_in_use"
        @unknown default: return "unknown"
        }
    }

    private func finish(_ payload: [String: Any]) {
        guard !finished else { return }
        finished = true
        manager.stopUpdatingLocation()
        geocoder?.cancelGeocode()

        do {
            let data = try JSONSerialization.data(withJSONObject: payload, options: [])
            if let text = String(data: data, encoding: .utf8) {
                print(text)
            } else {
                print("{\"ok\":false,\"error\":\"encoding_failure\"}")
            }
        } catch {
            print("{\"ok\":false,\"error\":\"json_failure\"}")
        }

        fflush(stdout)
        CFRunLoopStop(CFRunLoopGetMain())
    }

    private func fail(_ message: String) {
        finish([
            "ok": false,
            "error": message,
            "authorization": authorizationName(manager.authorizationStatus),
        ])
    }

    private func handleAuthorization() {
        switch manager.authorizationStatus {
        case .notDetermined:
            // The helper activates only while the OS permission prompt is needed.
            NSApplication.shared.activate(ignoringOtherApps: true)
            manager.requestWhenInUseAuthorization()
        case .authorizedAlways, .authorizedWhenInUse:
            manager.requestLocation()
        case .denied:
            fail("location_permission_denied")
        case .restricted:
            fail("location_permission_restricted")
        @unknown default:
            fail("unknown_authorization_status")
        }
    }

    func start() {
        guard CLLocationManager.locationServicesEnabled() else {
            fail("location_services_disabled")
            return
        }
        handleAuthorization()
    }

    func timeout() {
        guard !finished else { return }
        fail("location_request_timed_out")
    }

    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        guard !finished else { return }
        handleAuthorization()
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        fail("location_update_failed: " + error.localizedDescription)
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard !finished else { return }
        guard let location = locations.last(where: { $0.horizontalAccuracy >= 0 }) else {
            fail("no_valid_location")
            return
        }

        var payload: [String: Any] = [
            "ok": true,
            "latitude": location.coordinate.latitude,
            "longitude": location.coordinate.longitude,
            "horizontal_accuracy_m": location.horizontalAccuracy,
            "altitude_m": location.altitude,
            "timestamp": NSISO8601DateFormatter().string(from: location.timestamp),
            "authorization": authorizationName(manager.authorizationStatus),
        ]

        // LOCATION-1 resolves locality only. Street address is intentionally
        // excluded; precise delivery-address resolution belongs to ADDRESS-1.
        let localGeocoder = CLGeocoder()
        geocoder = localGeocoder
        localGeocoder.reverseGeocodeLocation(location) { [weak self] placemarks, _ in
            guard let self = self else { return }
            if let placemark = placemarks?.first {
                if let locality = placemark.locality { payload["locality"] = locality }
                if let area = placemark.administrativeArea { payload["administrative_area"] = area }
                if let country = placemark.country { payload["country"] = country }
                if let code = placemark.isoCountryCode { payload["iso_country_code"] = code }
            }
            self.finish(payload)
        }
    }
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)
app.finishLaunching()
let delegate = KumaLocationDelegate()
DispatchQueue.main.async { delegate.start() }
DispatchQueue.main.asyncAfter(deadline: .now() + 18.0) { delegate.timeout() }
RunLoop.main.run()
