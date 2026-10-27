#[path = "../../../experiments/002/server/mod.rs"]
mod stage1;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    stage1::main()
}
