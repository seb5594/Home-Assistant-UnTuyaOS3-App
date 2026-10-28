"""Track bytes sent without treating transmission as proof of installation."""


class TransferProgress:
    def __init__(self, total):
        if total <= 0:
            raise ValueError("Empty OTA image")
        self.total = total
        self.ranges = []

    def record(self, offset, length):
        if offset < 0 or length <= 0 or offset + length > self.total:
            raise ValueError("OTA byte range outside the image")
        merged = []
        for start, end in sorted([*self.ranges, (offset, offset + length)]):
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
            else:
                merged.append((start, end))
        self.ranges = merged

    @property
    def complete(self):
        return self.ranges == [(0, self.total)]

    def incomplete_result(self):
        if self.complete:
            print("All firmware bytes were sent, but OTA completion was not confirmed by the device. "
                  "Check for a Kickstart Wi-Fi network and verify boot before retrying; do not assume the flash failed.", flush=True)
            return 3
        sent = sum(end - start for start, end in self.ranges)
        print(f"OTA stopped after sending {sent}/{self.total} unique bytes. Device state is unknown; "
              "do not automatically retry or interrupt a device that may still be writing.", flush=True)
        return 1
