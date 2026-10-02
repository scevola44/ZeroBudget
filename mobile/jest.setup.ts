// In-memory stand-ins for the two native stores, reset between tests, so
// storage behaviour is observable without a device.
jest.mock("@react-native-async-storage/async-storage", () =>
  require("@react-native-async-storage/async-storage/jest/async-storage-mock"),
);

jest.mock("expo-secure-store", () => {
  const items = new Map<string, string>();
  return {
    __items: items,
    getItemAsync: jest.fn(async (key: string) => items.get(key) ?? null),
    setItemAsync: jest.fn(async (key: string, value: string) => {
      items.set(key, value);
    }),
    deleteItemAsync: jest.fn(async (key: string) => {
      items.delete(key);
    }),
  };
});

beforeEach(async () => {
  const AsyncStorage = require("@react-native-async-storage/async-storage");
  await AsyncStorage.clear();
  require("expo-secure-store").__items.clear();
});
